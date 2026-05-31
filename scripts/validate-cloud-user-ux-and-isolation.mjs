#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const DEFAULT_BANNED_TERMS = [
  "adapter",
  "bridge",
  "session JSONL",
  "source_thread",
  "canonical",
  "requested id",
  "raw UUID",
  "local path",
  "待审",
  "审批",
  "人工审核",
  "触发式派单",
  "Claude prompt",
  "显示场景",
  "隐藏功能",
  "合格性 D",
  "康复机械臂总控台",
];

function parseArgs(argv) {
  const args = {
    webBase: "http://106.55.62.122:3001",
    apiBase: "http://106.55.62.122:8011",
    projectId: "fe9bd342-f5ef-4afe-9c73-e7caa2ed17dd",
    compareProjectId: "",
    loginEmail: "3245056131@qq.com",
    loginPassword: "password",
    outsiderEmail: "",
    outsiderPassword: "",
    ensureOutsiderEmail: "",
    ensureOutsiderPassword: "password",
    ensureOutsiderName: "UX Isolation Outsider",
    outputDir: path.join(process.env.USERPROFILE || process.cwd(), ".codex", "automations", "ai-2", "artifacts", "cloud-user-ux-isolation"),
    desktopWidth: 1440,
    desktopHeight: 1000,
    mobileWidth: 390,
    mobileHeight: 900,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const next = argv[i + 1];
    if (!key.startsWith("--")) continue;
    if (next === undefined || next.startsWith("--")) {
      args[key.slice(2)] = "true";
      continue;
    }
    args[key.slice(2)] = next;
    i += 1;
  }
  return args;
}

async function requestJson(url, { method = "GET", payload, token } = {}) {
  const headers = { Accept: "application/json" };
  const options = { method, headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (payload !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(url, options);
  const text = await response.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }
  if (!response.ok) {
    const message = body?.error?.message || body?.message || text || `HTTP ${response.status}`;
    const error = new Error(`${method} ${url} failed: ${message}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

async function apiLogin(apiBase, email, password) {
  const payload = await requestJson(`${apiBase.replace(/\/$/, "")}/api/auth/session`, {
    method: "POST",
    payload: { email, password },
  });
  const token = payload?.data?.access_token;
  if (!token) throw new Error(`No access token returned for ${email}`);
  return payload.data;
}

async function ensureOutsiderAccount(args) {
  if (!args.ensureOutsiderEmail) return null;
  try {
    await apiLogin(args.apiBase, args.ensureOutsiderEmail, args.ensureOutsiderPassword);
    return {
      email: args.ensureOutsiderEmail,
      password: args.ensureOutsiderPassword,
      created: false,
    };
  } catch (error) {
    if (error.status && error.status !== 401 && error.status !== 404) throw error;
  }
  await requestJson(`${args.apiBase.replace(/\/$/, "")}/api/auth/register`, {
    method: "POST",
    payload: {
      email: args.ensureOutsiderEmail,
      name: args.ensureOutsiderName,
      password: args.ensureOutsiderPassword,
      global_role: "member",
    },
  });
  await apiLogin(args.apiBase, args.ensureOutsiderEmail, args.ensureOutsiderPassword);
  return {
    email: args.ensureOutsiderEmail,
    password: args.ensureOutsiderPassword,
    created: true,
  };
}

async function login(page, webBase, email, password) {
  await page.goto(`${webBase}/login`, { waitUntil: "domcontentloaded" });
  await page.fill('input[name="email"], input[type="email"], input[inputmode="email"]', email);
  await page.fill('input[name="password"], input[type="password"]', password);
  await Promise.allSettled([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 10000 }),
    page.click('button[type="submit"], button:has-text("登录")'),
  ]);
  await page.waitForTimeout(1500);
}

async function inspectPage(page, name, url, outputDir, bannedTerms = DEFAULT_BANNED_TERMS) {
  if (url) {
    await page.goto(url, { waitUntil: "networkidle", timeout: 45000 }).catch(async () => {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
    });
    await page.waitForTimeout(1200);
  }
  const screenshot = path.join(outputDir, `${name}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  const state = await page.evaluate((terms) => {
    const text = document.body?.innerText || "";
    const overflowX = Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth);
    return {
      url: location.href,
      title: document.title,
      textLength: text.length,
      blank: text.trim().length < 80,
      overflowX,
      hits: terms.filter((term) => text.includes(term)),
      contains: {
        terminal: text.includes("终端"),
        dataset: text.includes("数据标注"),
        chart: text.includes("图表实验"),
        npcNeeds: text.includes("我的需求"),
        npcTasks: text.includes("我的任务"),
        dialogue: text.includes("对话"),
      },
    };
  }, bannedTerms);
  return { name, screenshot, ...state };
}

async function clickFirstNpcAndInspect(page, webBase, projectId, outputDir) {
  await page.goto(`${webBase}/projects/${projectId}/workbench`, { waitUntil: "networkidle", timeout: 45000 }).catch(async () => {});
  await page.waitForTimeout(1200);
  const npcButton = page.locator('button[title*="NPC"]').filter({ hasText: /^\s*\d+号\s*NPC\b/ }).first();
  let clickResult = { clicked: false, text: "" };
  if (await npcButton.count()) {
    const text = (await npcButton.innerText()).trim().slice(0, 120);
    await npcButton.scrollIntoViewIfNeeded();
    await npcButton.click();
    clickResult = { clicked: true, text };
    await page.locator("text=我的需求").first().waitFor({ timeout: 5000 }).catch(async () => {
      await page.waitForTimeout(1000);
    });
  } else {
    const candidates = await page.locator("button").evaluateAll((nodes) => nodes.slice(0, 30).map((node) => (node.textContent || "").trim()));
    clickResult = { clicked: false, text: `no existing NPC chip button; candidates=${JSON.stringify(candidates)}` };
  }
  const result = await inspectPage(page, "workbench-after-npc-click", "", outputDir);
  result.clickResult = clickResult;
  result.npcTileContractOk = Boolean(
    clickResult.clicked
      && result.url.includes("/workbench")
      && result.contains.dialogue
      && result.contains.npcNeeds
      && result.contains.npcTasks,
  );
  return result;
}

function assertPageResult(result) {
  const problems = [];
  if (result.blank) problems.push("blank page");
  if (result.overflowX > 0) problems.push(`horizontal overflow ${result.overflowX}px`);
  if (result.hits?.length) problems.push(`banned terms: ${result.hits.join(", ")}`);
  return problems;
}

async function main() {
  const args = parseArgs(process.argv);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const outputDir = path.resolve(args.outputDir, stamp);
  await fs.mkdir(outputDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: Number(args.desktopWidth), height: Number(args.desktopHeight) },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const report = {
    createdAt: new Date().toISOString(),
    webBase: args.webBase,
    projectId: args.projectId,
    compareProjectId: args.compareProjectId || null,
    outputDir,
    results: [],
    issues: [],
    skipped: [],
    ensuredOutsider: null,
  };

  try {
    const ensuredOutsider = await ensureOutsiderAccount(args);
    if (ensuredOutsider) {
      report.ensuredOutsider = {
        email: ensuredOutsider.email,
        created: ensuredOutsider.created,
      };
      args.outsiderEmail = ensuredOutsider.email;
      args.outsiderPassword = ensuredOutsider.password;
    }

    await login(page, args.webBase, args.loginEmail, args.loginPassword);
    const paths = [
      ["main-desktop", `/projects/${args.projectId}`],
      ["2d-desktop", `/projects/${args.projectId}/2d-upgrade`],
      ["company-desktop", `/projects/${args.projectId}/company`],
      ["workbench-desktop", `/projects/${args.projectId}/workbench`],
      ["robotics-desktop", `/projects/${args.projectId}/robotics`],
      ["skill-forge-desktop", `/projects/${args.projectId}/skill-forge`],
    ];

    for (const [name, route] of paths) {
      const result = await inspectPage(page, name, `${args.webBase}${route}`, outputDir);
      report.results.push(result);
      const problems = assertPageResult(result);
      if (problems.length) report.issues.push({ name, problems });
    }

    const npcResult = await clickFirstNpcAndInspect(page, args.webBase, args.projectId, outputDir);
    report.results.push(npcResult);
    const npcProblems = assertPageResult(npcResult);
    if (!npcResult.npcTileContractOk) npcProblems.push("NPC tile contract missing dialogue/my-needs/my-tasks");
    if (npcProblems.length) report.issues.push({ name: npcResult.name, problems: npcProblems });

    await page.setViewportSize({ width: Number(args.mobileWidth), height: Number(args.mobileHeight) });
    const mobileResult = await inspectPage(page, "main-mobile", `${args.webBase}/projects/${args.projectId}`, outputDir);
    report.results.push(mobileResult);
    const mobileProblems = assertPageResult(mobileResult);
    if (mobileProblems.length) report.issues.push({ name: mobileResult.name, problems: mobileProblems });

    if (args.compareProjectId) {
      await page.setViewportSize({ width: Number(args.desktopWidth), height: Number(args.desktopHeight) });
      const compareResult = await inspectPage(
        page,
        "compare-project-robotics",
        `${args.webBase}/projects/${args.compareProjectId}/robotics`,
        outputDir,
        [...DEFAULT_BANNED_TERMS, "nanopi-cloud-smoke", "Windows COM30", "1号 NPC"],
      );
      report.results.push(compareResult);
      const compareProblems = assertPageResult(compareResult);
      if (compareProblems.length) report.issues.push({ name: compareResult.name, problems: compareProblems });
    } else {
      report.skipped.push("project isolation compare: pass --compareProjectId to validate another project surface");
    }

    if (args.outsiderEmail && args.outsiderPassword) {
      const outsiderContext = await browser.newContext({
        viewport: { width: Number(args.desktopWidth), height: Number(args.desktopHeight) },
        deviceScaleFactor: 1,
      });
      const outsiderPage = await outsiderContext.newPage();
      await login(outsiderPage, args.webBase, args.outsiderEmail, args.outsiderPassword);
      const outsiderProjects = await inspectPage(outsiderPage, "outsider-projects", `${args.webBase}/projects`, outputDir, [
        ...DEFAULT_BANNED_TERMS,
        args.projectId,
        "Windows COM30",
        "nanopi-cloud-smoke",
        "1号 NPC",
      ]);
      report.results.push(outsiderProjects);
      const outsiderProblems = assertPageResult(outsiderProjects);
      await outsiderPage.goto(`${args.webBase}/projects/${args.projectId}`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await outsiderPage.waitForTimeout(1200);
      const outsiderDirect = await inspectPage(outsiderPage, "outsider-direct-project", outsiderPage.url(), outputDir, [
        ...DEFAULT_BANNED_TERMS,
        "Windows COM30",
        "nanopi-cloud-smoke",
      ]);
      report.results.push(outsiderDirect);
      outsiderProblems.push(...assertPageResult(outsiderDirect));
      if (!outsiderDirect.url.includes("/projects") || outsiderDirect.url.includes(args.projectId)) {
        outsiderProblems.push("outsider direct-open did not leave protected project route");
      }
      if (outsiderProblems.length) report.issues.push({ name: "outsider-account-isolation", problems: outsiderProblems });
      await outsiderContext.close();
    } else {
      report.skipped.push("account isolation: pass --outsiderEmail and --outsiderPassword to validate another account without creating users");
    }
  } finally {
    await browser.close();
  }

  const reportPath = path.join(outputDir, "report.json");
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ ok: report.issues.length === 0, reportPath, issues: report.issues, skipped: report.skipped }, null, 2));
  if (report.issues.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
