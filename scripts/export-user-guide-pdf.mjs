import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const root = path.resolve("D:/ai合作产品");
const input = path.join(root, "docs", "USER_GUIDE.md");
const outDir = path.join(root, "docs");
const htmlPath = path.join(outDir, "USER_GUIDE.pdf.html");
const pdfPath = path.join(outDir, "USER_GUIDE.pdf");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inlineMd(value) {
  let text = escapeHtml(value);
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return text;
}

function renderTable(lines, startIndex) {
  const rows = [];
  let index = startIndex;
  while (index < lines.length && /^\|.*\|$/.test(lines[index].trim())) {
    rows.push(lines[index].trim());
    index += 1;
  }
  const htmlRows = rows
    .filter((row, rowIndex) => rowIndex !== 1 || !/^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$/.test(row))
    .map((row, rowIndex) => {
      const cells = row.slice(1, -1).split("|").map((cell) => inlineMd(cell.trim()));
      const tag = rowIndex === 0 ? "th" : "td";
      return `<tr>${cells.map((cell) => `<${tag}>${cell}</${tag}>`).join("")}</tr>`;
    });
  return {
    html: `<table>${htmlRows.join("\n")}</table>`,
    nextIndex: index,
  };
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let list = [];
  let inCode = false;
  let codeLines = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    output.push(`<p>${inlineMd(paragraph.join(" ").replace(/\s{2,}/g, " "))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!list.length) return;
    output.push(`<ul>${list.map((item) => `<li>${inlineMd(item)}</li>`).join("")}</ul>`);
    list = [];
  }

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i];
    const line = raw.trimEnd();

    if (line.startsWith("```")) {
      if (inCode) {
        output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(raw);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      flushParagraph();
      flushList();
      const alt = escapeHtml(imageMatch[1]);
      const srcPath = imageMatch[2].startsWith(".")
        ? path.join(path.dirname(input), imageMatch[2])
        : imageMatch[2];
      const src = pathToFileURL(path.resolve(srcPath)).href;
      output.push(`<figure><img src="${src}" alt="${alt}" /><figcaption>${alt}</figcaption></figure>`);
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      flushParagraph();
      flushList();
      const level = Math.min(line.match(/^#+/)?.[0].length ?? 1, 4);
      const text = line.replace(/^#{1,6}\s+/, "");
      output.push(`<h${level}>${inlineMd(text)}</h${level}>`);
      continue;
    }

    if (/^\|.*\|$/.test(line.trim()) && i + 1 < lines.length && /^\|\s*:?-{3,}:?/.test(lines[i + 1].trim())) {
      flushParagraph();
      flushList();
      const table = renderTable(lines, i);
      output.push(table.html);
      i = table.nextIndex - 1;
      continue;
    }

    if (/^-\s+/.test(line)) {
      flushParagraph();
      list.push(line.replace(/^-\s+/, ""));
      continue;
    }

    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  if (inCode) output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  return output.join("\n");
}

const markdown = fs.readFileSync(input, "utf8");
const body = renderMarkdown(markdown);
const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>AI 协作平台用户手册</title>
<style>
  @page { size: A4; margin: 14mm 12mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
    color: #17202a;
    line-height: 1.62;
    font-size: 12.5px;
  }
  h1 {
    font-size: 28px;
    margin: 0 0 12px;
    color: #07111f;
    border-bottom: 3px solid #1d6fd8;
    padding-bottom: 10px;
  }
  h2 {
    break-after: avoid;
    margin: 28px 0 10px;
    font-size: 20px;
    color: #0f355c;
    border-left: 5px solid #1d6fd8;
    padding-left: 10px;
  }
  h3 {
    break-after: avoid;
    margin: 18px 0 8px;
    font-size: 15px;
    color: #173b5f;
  }
  p { margin: 7px 0; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 14px;
    break-inside: avoid;
  }
  th, td {
    border: 1px solid #d6e0ea;
    padding: 6px 8px;
    vertical-align: top;
  }
  th {
    background: #eef5ff;
    color: #102a43;
    font-weight: 700;
  }
  ul {
    margin: 8px 0 12px 22px;
    padding: 0;
  }
  li { margin: 3px 0; }
  code {
    font-family: Consolas, "Courier New", monospace;
    background: #f3f6f9;
    padding: 1px 4px;
    border-radius: 3px;
    color: #9a3412;
  }
  pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 10px 12px;
    border-radius: 6px;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
    break-inside: avoid;
  }
  figure {
    margin: 12px 0 18px;
    break-inside: avoid;
  }
  img {
    display: block;
    max-width: 100%;
    max-height: 215mm;
    object-fit: contain;
    border: 1px solid #d7dee8;
    border-radius: 5px;
  }
  figcaption {
    margin-top: 5px;
    color: #5b6775;
    font-size: 11px;
    text-align: center;
  }
</style>
</head>
<body>
${body}
</body>
</html>`;

fs.writeFileSync(htmlPath, html, "utf8");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
await page.pdf({
  path: pdfPath,
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();
console.log(pdfPath);
