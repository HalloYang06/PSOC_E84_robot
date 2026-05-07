// validate-all-buttons.mjs
// 第二轮验收：按钮 / 链接 / 跳转 一一冒烟，每个 PASS/FAIL + 前后两张截图。
//
// 用户原话（2026-05-07）：
//   "你所有按键都验收一遍吧，别在后端欺骗自己了"
//
// 触达点（参考 handoff-truth-and-pending-2026-05-07.md 的 E 表）。
// 这一轮先覆盖最关键的 12 项，后续可补；FAIL 不藏。

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3100").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT_DIR = path.resolve("artifacts", "all-buttons-validation");
fs.mkdirSync(OUT_DIR, { recursive: true });

const ACCESS_COOKIE = "farm_access_token"; // BFF proxy 只认这个名字

// ---- helpers ----
async function login(context) {
  const r = await context.request.post(`${API}/api/auth/session`, {
    data: { email: EMAIL, password: PASSWORD },
    headers: { "Content-Type": "application/json" },
  });
  if (!r.ok()) throw new Error(`login HTTP ${r.status()}: ${await r.text()}`);
  const body = await r.json();
  return body.data.access_token;
}

async function shoot(page, name) {
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

const results = []; // { id, label, before, after, pass, note }

function record(id, label, before, after, pass, note = "") {
  results.push({ id, label, before, after, pass, note });
  const tag = pass ? "PASS" : "FAIL";
  console.log(`[${tag}] #${id} ${label}${note ? "  — " + note : ""}`);
}

async function safe(label, fn) {
  try {
    return await fn();
  } catch (err) {
    console.log(`  · ${label} threw: ${err.message}`);
    return null;
  }
}

// ---- main ----
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1100 },
    locale: "zh-CN",
  });

  // 先用 API 拿 token，注入到 web 域 cookie；这样 BFF proxy 能把 cookie 转 Bearer
  const token = await login(ctx);
  for (const host of ["127.0.0.1", "localhost"]) {
    await ctx.addCookies([
      {
        name: ACCESS_COOKIE,
        value: token,
        domain: host,
        path: "/",
        httpOnly: false, // server 也能读；测试场景不需要 httpOnly
        secure: false,
        sameSite: "Lax",
      },
    ]);
  }

  const page = await ctx.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("[console.error]", msg.text());
  });

  // ---- #1 登录页可达（用全新无 cookie context，否则已登录态会被 redirect 走）----
  {
    const guestCtx = await browser.newContext({
      viewport: { width: 1600, height: 1100 },
      locale: "zh-CN",
    });
    const guestPage = await guestCtx.newPage();
    await guestPage.goto(`${WEB}/login`, { waitUntil: "networkidle", timeout: 30000 });
    await guestPage.waitForTimeout(800);
    const before = path.join(OUT_DIR, "01-login-before.png");
    await guestPage.screenshot({ path: before, fullPage: true });
    const hasForm = await guestPage.locator('input[name="email"], input[type="email"]').count();
    const hasPwd = await guestPage.locator('input[name="password"], input[type="password"]').count();
    const after = path.join(OUT_DIR, "01-login-after.png");
    await guestPage.screenshot({ path: after, fullPage: true });
    record("01", "登录页（无登录态）有 email + password 输入框",
      before, after, hasForm > 0 && hasPwd > 0,
      `email=${hasForm} pwd=${hasPwd}`);
    await guestCtx.close();
  }

  // ---- #2 项目列表可达（用 cookie 已登录态） ----
  {
    await page.goto(`${WEB}/projects`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(1500);
    const before = await shoot(page, "02-projects-list-before");
    const url = page.url();
    const onProjects = url.includes("/projects") && !url.includes("/login");
    const after = await shoot(page, "02-projects-list-after");
    record("02", "项目列表可达（已登录态）", before, after, onProjects,
      onProjects ? `URL=${url}` : `被踢回 ${url}`);
  }

  // ---- #3 驾驶舱页（cockpit）—— 死循环 BUG 是否修好 ----
  {
    await page.goto(`${WEB}/projects/${PROJECT}/cockpit`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2000);
    const before = await shoot(page, "03-cockpit-before");
    const url = page.url();
    const stillCockpit = url.includes("/cockpit");
    const hasOpenWorkbench = (await page.getByText("打开工作台").count()) > 0;
    const after = await shoot(page, "03-cockpit-after");
    record("03", "/projects/{id}/cockpit 真驾驶舱可达（不死循环）", before, after,
      stillCockpit && hasOpenWorkbench,
      stillCockpit ? "" : `被打到 ${url}`);
  }

  // ---- #4 工作台可达 ----
  {
    await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2500);
    const before = await shoot(page, "04-workbench-before");
    const url = page.url();
    const hasBackToCockpit = await page.locator('a[title="返回项目驾驶舱"]').count();
    const after = await shoot(page, "04-workbench-after");
    record("04", "工作台 /workbench 可达 + 顶部有 ← 驾驶舱", before, after,
      url.includes("/workbench") && hasBackToCockpit > 0,
      `URL=${url} backLinks=${hasBackToCockpit}`);
  }

  // ---- #5 工作台 "← 驾驶舱" 跳到 cockpit（修死循环）----
  {
    const before = await shoot(page, "05-back-to-cockpit-before");
    await safe("click backLink", () => page.locator('a[title="返回项目驾驶舱"]').first().click());
    await page.waitForTimeout(1500);
    const url = page.url();
    const after = await shoot(page, "05-back-to-cockpit-after");
    record("05", "工作台 ← 驾驶舱 跳到 /cockpit（不再打回 workbench）",
      before, after, url.endsWith("/cockpit") || url.includes("/cockpit"),
      `URL=${url}`);
  }

  // ---- #6 cockpit "打开工作台 →" 回到工作台 ----
  {
    const before = await shoot(page, "06-cockpit-to-workbench-before");
    await safe("click 打开工作台", () => page.getByText("打开工作台").first().click());
    await page.waitForTimeout(1500);
    const url = page.url();
    const after = await shoot(page, "06-cockpit-to-workbench-after");
    record("06", "cockpit 打开工作台 → /workbench", before, after,
      url.includes("/workbench"), `URL=${url}`);
  }

  // ---- #7 + 号开瓷砖 ----
  {
    const before = await shoot(page, "07-open-tiles-before");
    const plusBtns = page.locator('button[title="打开瓷砖"]');
    const cnt = await plusBtns.count();
    for (let i = 0; i < Math.min(cnt, 2); i++) {
      await safe(`click +${i}`, () => plusBtns.nth(i).click());
      await page.waitForTimeout(700);
    }
    await page.waitForTimeout(2500);
    const tiles = await page.locator('[class*="npcTile_tile"], [class*="tile"][class*="card"]').count();
    const composers = await page.locator('textarea[placeholder*="发指令"]').count();
    const after = await shoot(page, "07-open-tiles-after");
    record("07", "+ 号开瓷砖（找到 composer textarea）", before, after,
      composers > 0, `+按钮=${cnt} composer=${composers} tiles=${tiles}`);
  }

  // ---- #8 占用锁 badge 出现 ----
  {
    const before = await shoot(page, "08-occupancy-badge-before");
    await page.waitForTimeout(2500);
    // NpcTile 实际文案：🟢 你正在占用此 NPC / 🟡 X 正在占用 / ⚪ 空闲，可占用
    const occBars = await page.locator('text=/(正在占用|空闲，可占用|准备占用)/').count();
    const after = await shoot(page, "08-occupancy-badge-after");
    record("08", "瓷砖打开后出现占用状态 badge", before, after,
      occBars > 0, `badge=${occBars}`);
  }

  // ---- #9 收起档案 ----
  {
    const before = await shoot(page, "09-collapse-profile-before");
    const collapse = page.locator('button:has-text("收起档案")');
    const cc = await collapse.count();
    for (let i = 0; i < cc; i++) {
      await safe(`collapse ${i}`, () => collapse.nth(i).click());
      await page.waitForTimeout(300);
    }
    await page.waitForTimeout(800);
    const expand = await page.locator('button:has-text("展开档案")').count();
    const after = await shoot(page, "09-collapse-profile-after");
    record("09", "收起档案后变 \"展开档案\"", before, after,
      cc > 0 && expand > 0, `before收起=${cc} after展开=${expand}`);
  }

  // ---- #10 派单输入框 + Ctrl+Enter ----
  {
    const before = await shoot(page, "10-dispatch-before");
    const ta = page.locator('textarea[placeholder*="发指令"]').first();
    const exists = await ta.count();
    let posted = false;
    if (exists > 0) {
      await safe("fill ta", () => ta.fill(`[validate-all-buttons] 冒烟测试 ${Date.now()}`));
      await safe("ctrl+enter", () => ta.press("Control+Enter"));
      await page.waitForTimeout(2500);
      posted = (await ta.inputValue()) === "";
    }
    const after = await shoot(page, "10-dispatch-after");
    record("10", "派单 textarea + Ctrl+Enter 发送（输入框清空 = 已提交）",
      before, after, exists > 0 && posted,
      `textarea=${exists} cleared=${posted}`);
  }

  // ---- #11 cockpit 顶部"← 项目列表"回到 /projects ----
  {
    // 走一遍：workbench → ← 驾驶舱 → cockpit 顶部"← 项目列表"
    await page.goto(`${WEB}/projects/${PROJECT}/cockpit`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(1500);
    const before = await shoot(page, "11-back-to-list-before");
    const link = page.locator('a[href="/projects"]').first();
    const linkCount = await page.locator('a[href="/projects"]').count();
    let url = page.url();
    if (linkCount > 0) {
      await safe("click projects link", () => link.click());
      await page.waitForTimeout(1500);
      url = page.url();
    }
    const after = await shoot(page, "11-back-to-list-after");
    const ok = url.endsWith("/projects") || /\/projects(\?|$)/.test(url);
    record("11", "cockpit ← 项目列表 → /projects", before, after, ok,
      `linkCount=${linkCount} URL=${url}`);
  }

  // ---- #12 退出登录（如有按钮）----
  {
    await page.goto(`${WEB}/projects`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(1200);
    const before = await shoot(page, "12-logout-before");
    const logout = page.locator('button:has-text("退出"), a:has-text("退出"), button:has-text("登出")');
    const lc = await logout.count();
    let landed = false;
    if (lc > 0) {
      await safe("click logout", () => logout.first().click());
      await page.waitForTimeout(1500);
      landed = page.url().includes("/login");
    }
    const after = await shoot(page, "12-logout-after");
    record("12", "退出登录按钮可见且点击后回 /login",
      before, after, lc > 0 && landed,
      lc > 0 ? `URL=${page.url()}` : "未找到退出按钮（v1 可能未做）");
  }

  // ---- 收尾报告 ----
  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass).length;
  const reportPath = path.join(OUT_DIR, "report.md");
  const lines = [
    `# 按钮全验收报告（validate-all-buttons.mjs）`,
    ``,
    `运行：${new Date().toISOString()}  ·  PROJECT=${PROJECT}  ·  WEB=${WEB}`,
    ``,
    `**汇总：${pass} PASS / ${fail} FAIL（共 ${results.length}）**`,
    ``,
    `| # | 按钮/链接 | 结果 | 说明 | 截图前 | 截图后 |`,
    `|---|---|---|---|---|---|`,
    ...results.map((r) => {
      const before = path.basename(r.before);
      const after = path.basename(r.after);
      return `| ${r.id} | ${r.label} | ${r.pass ? "✅ PASS" : "❌ FAIL"} | ${r.note || ""} | ![b](${before}) | ![a](${after}) |`;
    }),
  ];
  fs.writeFileSync(reportPath, lines.join("\n"));
  console.log(`\n→ 报告：${reportPath}`);
  console.log(`→ 截图目录：${OUT_DIR}`);
  console.log(`\n汇总：${pass} PASS / ${fail} FAIL`);

  await ctx.close();
  await browser.close();
  process.exit(fail > 0 ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
