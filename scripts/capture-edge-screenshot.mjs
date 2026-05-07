import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const EDGE_PATHS = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const part = argv[i];
    if (!part.startsWith("--")) continue;
    const key = part.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true";
    out[key] = value;
  }
  return out;
}

function findEdge() {
  for (const candidate of EDGE_PATHS) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("Microsoft Edge not found");
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchText(url, attempts = 30) {
  let lastError;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.text();
      }
    } catch (error) {
      lastError = error;
    }
    await wait(400);
  }
  throw lastError ?? new Error(`Failed to fetch ${url}`);
}

async function main() {
  const args = parseArgs(process.argv);
  const url = String(args.url ?? "").trim();
  const output = String(args.output ?? "").trim();
  const htmlDump = String(args["html-dump"] ?? "").trim();
  const textDump = String(args["text-dump"] ?? "").trim();
  const markers = String(args.markers ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
  const width = Number(args["viewport-width"] ?? 1680) || 1680;
  const height = Number(args["viewport-height"] ?? 1260) || 1260;
  const budget = Number(args["virtual-time-budget"] ?? 12000) || 12000;

  if (!url || !output) {
    throw new Error("Usage: node capture-edge-screenshot.mjs --url <url> --output <png> [--markers a|b]");
  }

  fs.mkdirSync(path.dirname(output), { recursive: true });
  if (htmlDump) fs.mkdirSync(path.dirname(htmlDump), { recursive: true });
  if (textDump) fs.mkdirSync(path.dirname(textDump), { recursive: true });

  const html = await fetchText(url);
  if (htmlDump) {
    fs.writeFileSync(htmlDump, html, "utf8");
  }
  if (textDump) {
    const text = html.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ");
    fs.writeFileSync(textDump, text, "utf8");
  }
  if (markers.length) {
    const missing = markers.filter((marker) => !html.includes(marker));
    if (missing.length) {
      throw new Error(`Markers not found: ${missing.join(", ")}`);
    }
  }

  const edge = findEdge();
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-edge-capture-"));
  const child = spawn(
    edge,
    [
      "--headless",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${userDataDir}`,
      `--window-size=${width},${height}`,
      `--virtual-time-budget=${budget}`,
      `--screenshot=${output}`,
      url,
    ],
    {
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  let stderr = "";
  let stdout = "";
  child.stdout?.on("data", (chunk) => {
    stdout += String(chunk);
  });
  child.stderr?.on("data", (chunk) => {
    stderr += String(chunk);
  });

  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", resolve);
  });

  if (exitCode !== 0) {
    throw new Error(
      `Edge screenshot exited with code ${exitCode}${stderr ? `\nSTDERR:\n${stderr}` : ""}${stdout ? `\nSTDOUT:\n${stdout}` : ""}`,
    );
  }
  if (!fs.existsSync(output)) {
    throw new Error("Screenshot was not created");
  }

  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
