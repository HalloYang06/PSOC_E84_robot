// Current full-page frontend walk.
//
// Runs against a live API + web server and validates the current platform
// contract, not the old iframe GameShell contract.
//
// Usage:
//   $env:API_BASE='http://127.0.0.1:8010'
//   $env:WEB_BASE='http://127.0.0.1:3100'
//   node scripts\validate-all-pages-walk.mjs

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT = path.resolve("artifacts", "all-pages-walk-2026-05-08");

fs.mkdirSync(OUT, { recursive: true });

let stepIdx = 0;
function shotPath(name) {
  stepIdx += 1;
  return path.join(OUT, `${String(stepIdx).padStart(2, "0")}-${name}.png`);
}

function log(message) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${message}`);
}

async function login() {
  const response = await fetch(`${API}/api/auth/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!response.ok) throw new Error(`login HTTP ${response.status}: ${await response.text()}`);
  return (await response.json()).data.access_token;
}

async function readProjectName(token) {
  const response = await fetch(`${API}/api/projects/${encodeURIComponent(PROJECT)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) return null;
  const payload = await response.json().catch(() => null);
  const project = payload?.data ?? payload;
  const name = typeof project?.name === "string" ? project.name.trim() : "";
  return name || null;
}

function summarizeBodyState(markers) {
  return (markersArg) => {
    const body = document.body?.innerText || "";
    const root = document.scrollingElement || document.documentElement;
    return {
      href: location.href,
      bodyLen: body.length,
      preview: body.slice(0, 1200),
      missing: markersArg.filter((marker) => !body.includes(marker)),
      horizontalOverflow: root.scrollWidth > root.clientWidth + 2,
      buttons: Array.from(document.querySelectorAll("button"))
        .map((button) => (button.textContent || button.title || "").trim())
        .filter(Boolean)
        .slice(0, 80),
      links: Array.from(document.querySelectorAll("a"))
        .map((link) => (link.textContent || link.title || "").trim())
        .filter(Boolean)
        .slice(0, 80),
    };
  };
}

(async () => {
  const issues = [];
  const passes = [];

  function note(ok, message, detail = "") {
    const item = { message, detail };
    if (ok) {
      passes.push(item);
      log(`  ✓ ${message}${detail ? ` — ${detail}` : ""}`);
    } else {
      issues.push(item);
      log(`  ✗ ${message}${detail ? ` — ${detail}` : ""}`);
    }
  }

  log("登录");
  const token = await login();
  const projectName = await readProjectName(token);
  const projectShellMarkers = [...(projectName ? [projectName] : []), "NPC 工作台"];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: "zh-CN" });
  await context.addCookies([
    { name: "farm_access_token", value: token, url: `${WEB}/`, sameSite: "Lax" },
    {
      name: "farm_user",
      value: JSON.stringify({ id: "lead", name: "lead", email: EMAIL }),
      url: `${WEB}/`,
      sameSite: "Lax",
    },
  ]);

  const page = await context.newPage();
  page.on("pageerror", (error) => issues.push({ message: "PAGE-ERROR", detail: error.message }));
  page.on("console", (message) => {
    if (message.type() === "error") issues.push({ message: "CONSOLE-ERROR", detail: message.text().slice(0, 240) });
  });

  async function checkPage(id, route, markers, options = {}) {
    log(`\n[${id}] ${route}`);
    await page.goto(`${WEB}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(options.waitMs ?? 1200);
    const file = shotPath(id);
    await page.screenshot({ path: file, fullPage: Boolean(options.fullPage) });
    const state = await page.evaluate(summarizeBodyState(markers), markers);
    note(!state.href.includes("/login") || route === "/login", `${route} 不被异常踢回 login`, `url=${state.href}`);
    note(state.bodyLen > 100, `${route} 内容已加载`, `bodyLen=${state.bodyLen}`);
    note(state.missing.length === 0, `${route} 关键文案存在`, state.missing.length ? `missing=${state.missing.join(",")}` : "");
    note(!state.horizontalOverflow, `${route} 无横向溢出`);
    return state;
  }

  await checkPage("login-auth-redirect", "/login", ["选择项目"]);
  await checkPage("projects-list", "/projects", ["选择项目", "进入 AI 协作工作台"]);
  await checkPage("mode-choice", "/projects/mode-choice", ["项目"]);
  await checkPage("project-main", `/projects/${encodeURIComponent(PROJECT)}`, [...projectShellMarkers, "公司层"]);
  await checkPage("cockpit", `/projects/${encodeURIComponent(PROJECT)}/cockpit`, ["项目驾驶舱", "打开工作台", "设备数据工作台"]);
  const workbenchState = await checkPage("workbench", `/projects/${encodeURIComponent(PROJECT)}/workbench`, ["协同工作台", "Boss NPC 项目生成器"], { fullPage: true });
  note(workbenchState.buttons.some((button) => button.includes("+")), "工作台存在打开 NPC 瓷砖按钮");
  await checkPage("company", `/projects/${encodeURIComponent(PROJECT)}/company`, ["公司沙盘", "运行态势图"], { fullPage: true });
  await checkPage("robotics", `/projects/${encodeURIComponent(PROJECT)}/robotics`, ["设备数据工作台", "创建调试窗口", "绑定真实设备"], { fullPage: true });
  await checkPage("skill-forge", `/projects/${encodeURIComponent(PROJECT)}/skill-forge`, ["能力工坊", "Skill"], { fullPage: true });
  await checkPage("legacy-2d-upgrade", `/projects/${encodeURIComponent(PROJECT)}/2d-upgrade`, projectShellMarkers);

  await context.close();
  await browser.close();

  const reportPath = path.resolve("docs", "screenshots", "v1", "all-pages-walk-2026-05-08.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  const lines = [
    "# 全量页面 UX walk 报告（当前平台合同）",
    "",
    `- 时间：${new Date().toISOString()}`,
    `- 项目：${PROJECT}`,
    `- Web：${WEB}`,
    `- 总通过：${passes.length}`,
    `- 总问题：${issues.length}`,
    "",
    "## 通过项",
    "",
    ...passes.map((item) => `- ✓ ${item.message}${item.detail ? ` — ${item.detail}` : ""}`),
    "",
    "## 问题项",
    "",
    issues.length === 0 ? "_（无）_" : "",
    ...issues.map((item) => `- ✗ ${item.message}${item.detail ? ` — ${item.detail}` : ""}`),
    "",
    "## 截图",
    "",
    ...fs.readdirSync(OUT).filter((file) => file.endsWith(".png")).map((file) => `- \`${path.join(OUT, file)}\``),
  ];
  fs.writeFileSync(reportPath, lines.join("\n"), "utf8");
  log(`\n报告：${reportPath}`);
  log(`汇总：${passes.length} PASS / ${issues.length} FAIL`);
  process.exit(issues.length === 0 ? 0 : 1);
})().catch((error) => {
  console.error(error);
  process.exit(2);
});
