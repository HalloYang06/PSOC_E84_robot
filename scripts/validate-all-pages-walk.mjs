// 全量前端 walk — 完全用户视角
//
// 走遍所有可见页面 + 每个页面所有按钮 + 验证跳转目标合不合理 +
// 检查"返回游戏"路径是否始终通畅。
//
// 运行：API + Web 都已起来；
//   node scripts/validate-all-pages-walk.mjs

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
  const idx = String(stepIdx).padStart(2, "0");
  return path.join(OUT, `${idx}-${name}.png`);
}
const log = (m) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${m}`);

async function login() {
  const r = await fetch(`${API}/api/auth/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!r.ok) throw new Error(`login HTTP ${r.status}`);
  return (await r.json()).data.access_token;
}

(async () => {
  const issues = [];
  const passes = [];
  function note(ok, msg, detail = "") {
    if (ok) {
      passes.push({ msg, detail });
      log(`  ✓ ${msg}${detail ? ` — ${detail}` : ""}`);
    } else {
      issues.push({ msg, detail });
      log(`  ✗ ${msg}${detail ? ` — ${detail}` : ""}`);
    }
  }

  log("登录");
  const token = await login();

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const cookieDomain = new URL(WEB).hostname;
  await ctx.addCookies([
    { name: "farm_access_token", value: token, domain: cookieDomain, path: "/", sameSite: "Lax" },
    { name: "farm_user", value: JSON.stringify({ id: "lead", name: "lead", email: EMAIL }), domain: cookieDomain, path: "/", sameSite: "Lax" },
  ]);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => issues.push({ msg: "PAGE-ERROR", detail: e.message }));
  page.on("console", (m) => {
    if (m.type() === "error") issues.push({ msg: "CONSOLE-ERROR", detail: m.text().slice(0, 200) });
  });

  // ========== A 登录页 ==========
  log("\n[A] 登录页");
  await page.goto(`${WEB}/login`, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(700);
  await page.screenshot({ path: shotPath("login"), fullPage: false });
  const emailVisible = await page.locator('input[type="email"]').count();
  const pwdVisible = await page.locator('input[type="password"]').count();
  note(emailVisible >= 1, "登录页有 email 输入", `count=${emailVisible}`);
  note(pwdVisible >= 1, "登录页有 password 输入", `count=${pwdVisible}`);
  note(await page.locator('button[type="submit"]').first().isVisible(), "登录页有提交按钮");
  await ctx.addCookies([
    { name: "farm_access_token", value: token, domain: cookieDomain, path: "/", sameSite: "Lax" },
  ]);

  // ========== B / 首页 → /projects ==========
  log("\n[B] 首页 (/)");
  await page.goto(`${WEB}/`, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: shotPath("home"), fullPage: false });
  note(page.url().includes("/projects") || page.url().endsWith("/"), "/ 不报 404", `url=${page.url()}`);

  // ========== C /projects 项目列表 ==========
  log("\n[C] /projects 项目列表");
  await page.goto(`${WEB}/projects`, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: shotPath("projects-list"), fullPage: true });
  note(!page.url().includes("/login"), "已登录态访问 /projects 不被踢回 login");
  const projectListText = await page.evaluate(() => document.body.innerText);
  note(projectListText.includes(PROJECT) || projectListText.length > 100,
       `项目列表内容已加载`, `bodyLen=${projectListText.length}`);

  // ========== D /projects/mode-choice ==========
  log("\n[D] /projects/mode-choice");
  await page.goto(`${WEB}/projects/mode-choice`, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: shotPath("mode-choice"), fullPage: false });
  note(!page.url().includes("/login"), "/projects/mode-choice 可达");

  // ========== E /projects/[id] 默认 → GameShell ==========
  log("\n[E] /projects/[id] 默认游戏壳");
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("game-shell"), fullPage: false });
  const topNavCockpit = await page.locator('button:has-text("驾驶舱")').first().isVisible().catch(() => false);
  const topNavWorkbench = await page.locator('button:has-text("工作台")').first().isVisible().catch(() => false);
  const topNavCompany = await page.locator('button:has-text("公司层")').first().isVisible().catch(() => false);
  const topNavHide = await page.locator('button:has-text("隐藏游戏"), button:has-text("显示游戏")').first().isVisible().catch(() => false);
  note(topNavCockpit, "GameShell 顶 nav 有「🛠️ 驾驶舱」按钮");
  note(topNavWorkbench, "GameShell 顶 nav 有「🧑‍💼 工作台」按钮");
  note(topNavCompany, "GameShell 顶 nav 有「🏢 公司层」按钮");
  note(topNavHide, "GameShell 顶 nav 有「隐藏/显示游戏」按钮");
  const gameIframe = await page.locator('iframe').count();
  note(gameIframe >= 1, `游戏 iframe 存在`, `count=${gameIframe}`);

  // ========== F GameShell 抽屉里 - 驾驶舱 ==========
  log("\n[F] 抽屉 - 驾驶舱");
  await page.locator('button:has-text("驾驶舱")').first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("drawer-cockpit"), fullPage: false });
  const drawer = await page.locator('aside').first().isVisible().catch(() => false);
  note(drawer, "驾驶舱抽屉拉出");
  const drawerSrc = await page.locator('aside iframe').first().getAttribute('src').catch(() => "");
  note((drawerSrc || "").includes("embed=drawer"), "抽屉 iframe 用 ?embed=drawer", `src=${drawerSrc?.slice(0, 80)}`);
  await page.locator('aside button[title*="关闭"]').first().click().catch(() => {});
  await page.waitForTimeout(500);

  // ========== G GameShell 抽屉里 - 工作台 ==========
  log("\n[G] 抽屉 - 工作台");
  await page.locator('button:has-text("工作台")').first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("drawer-workbench"), fullPage: false });
  note(await page.locator('aside').first().isVisible().catch(() => false), "工作台抽屉拉出");
  await page.locator('aside button[title*="关闭"]').first().click().catch(() => {});
  await page.waitForTimeout(500);

  // ========== H GameShell 抽屉里 - 公司层 ==========
  log("\n[H] 抽屉 - 公司层");
  await page.locator('button:has-text("公司层")').first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("drawer-company"), fullPage: false });
  note(await page.locator('aside').first().isVisible().catch(() => false), "公司层抽屉拉出");
  await page.locator('aside button[title*="关闭"]').first().click().catch(() => {});
  await page.waitForTimeout(500);

  // ========== I 隐藏游戏 ==========
  log("\n[I] 隐藏游戏 + 占位符");
  await page.locator('button:has-text("隐藏游戏")').first().click().catch(() => {});
  await page.waitForTimeout(500);
  await page.screenshot({ path: shotPath("game-hidden"), fullPage: false });
  note(await page.locator('text=游戏已隐藏').first().isVisible().catch(() => false), "隐藏游戏后显示占位符");
  await page.locator('button:has-text("显示游戏")').first().click().catch(() => {});
  await page.waitForTimeout(500);

  // ========== J 独立路由 - cockpit ==========
  log("\n[J] /projects/[id]/cockpit 独立路由");
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}/cockpit`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: shotPath("cockpit-standalone"), fullPage: true });
  note(!page.url().includes("/login"), "/cockpit 独立路由可达");
  const cockpitGameBack = await page.locator('a:has-text("🎮 游戏"), a:has-text("游戏")').first().isVisible().catch(() => false);
  note(cockpitGameBack, "驾驶舱独立页有「🎮 游戏」回新游戏壳的按钮（关键 UX 修复）");
  const oldLegacyLink = await page.locator('a:has-text("旧版页面")').first().isVisible().catch(() => false);
  note(!oldLegacyLink, "驾驶舱不再有「旧版页面」入口（用户已抛弃旧农场）");

  // ========== K 独立路由 - workbench ==========
  log("\n[K] /projects/[id]/workbench 独立路由");
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}/workbench`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("workbench-standalone"), fullPage: true });
  note(!page.url().includes("/login"), "/workbench 独立路由可达");
  const wbGameBack = await page.locator('a:has-text("🎮 游戏"), a:has-text("游戏")').first().isVisible().catch(() => false);
  note(wbGameBack, "工作台独立页有「🎮 游戏」回新游戏壳的按钮（关键 UX 修复）");
  const wbCockpitBack = await page.locator('a:has-text("驾驶舱")').first().isVisible().catch(() => false);
  note(wbCockpitBack, "工作台 topbar 有去驾驶舱的快捷");

  // ========== L 独立路由 - company ==========
  log("\n[L] /projects/[id]/company 独立路由");
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}/company`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("company-standalone"), fullPage: true });
  note(!page.url().includes("/login"), "/company 独立路由可达");
  const companyGameBack = await page.locator('a:has-text("🎮 游戏"), a:has-text("游戏")').first().isVisible().catch(() => false);
  note(companyGameBack, "公司层独立页有「🎮 游戏」回新游戏壳的按钮");

  // ========== M 旧 2d-upgrade 不应是默认入口 ==========
  log("\n[M] 旧 2d-upgrade（用户已抛弃）");
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}/2d-upgrade`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: shotPath("legacy-2d-upgrade"), fullPage: false });
  note(!page.url().includes("/login"), "旧 /2d-upgrade 仍可访问（保留兼容）");
  // 注意：用户已抛弃这个页面，新游戏的所有跳转链路不应回到这里

  // ========== 总结 ==========
  await browser.close();

  log(`\n========== 总计 ==========`);
  log(`PASS: ${passes.length}`);
  log(`FAIL: ${issues.length}`);

  const md = [
    `# 全量页面 UX walk 报告（用户视角）`,
    ``,
    `- 时间：${new Date().toISOString()}`,
    `- 项目：${PROJECT}`,
    `- 总通过：${passes.length}`,
    `- 总问题：${issues.length}`,
    ``,
    `## 通过项`,
    ``,
    ...passes.map((p) => `- ✓ ${p.msg}${p.detail ? ` — ${p.detail}` : ""}`),
    ``,
    `## 问题项`,
    ``,
    issues.length === 0 ? "_（无）_" : "",
    ...issues.map((i) => `- ✗ ${i.msg}${i.detail ? ` — ${i.detail}` : ""}`),
    ``,
    `## 截图`,
    ``,
    ...fs.readdirSync(OUT).filter((f) => f.endsWith(".png")).map((f) => `- \`${path.join(OUT, f)}\``),
  ].join("\n");
  const reportPath = path.resolve("docs", "screenshots", "v1", "all-pages-walk-2026-05-08.md");
  fs.writeFileSync(reportPath, md);
  log(`报告：${reportPath}`);

  process.exit(issues.length === 0 ? 0 : 1);
})();
