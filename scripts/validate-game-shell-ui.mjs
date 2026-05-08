// Validate /projects/[id] now lands on GameShell, top nav opens drawer iframe.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT = path.resolve("artifacts", "game-shell-ui");
fs.mkdirSync(OUT, { recursive: true });

function ts(label) {
  return path.join(OUT, `${label}-${Date.now()}.png`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const log = (m) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${m}`);
  const result = { steps: [], pass: false };

  try {
    log(`open ${WEB}/projects/${PROJECT}`);
    await page.goto(`${WEB}/projects/${PROJECT}`, { waitUntil: "domcontentloaded" });

    // login form
    if (page.url().includes("/login")) {
      log("login redirect, filling form");
      await page.locator('input[type="email"]').first().fill(EMAIL);
      await page.locator('input[type="password"]').first().fill(PASSWORD);
      await Promise.all([
        page.waitForLoadState("networkidle"),
        page.locator('button[type="submit"]:has-text("进入项目空间")').first().click(),
      ]);
    }

    // wait for either GameShell topNav or legacy
    await page.waitForLoadState("networkidle");
    log(`landed at: ${page.url()}`);
    await page.screenshot({ path: ts("01-landing"), fullPage: false });

    const topNavExists = await page.locator('header').filter({ hasText: '驾驶舱' }).first().isVisible().catch(() => false);
    const iframeCount = await page.locator('iframe').count();
    result.steps.push({ name: "顶部 nav 显示「驾驶舱」按钮", ok: !!topNavExists });
    result.steps.push({ name: "页面内嵌 game iframe (≥1)", ok: iframeCount >= 1, detail: { iframeCount } });

    // click 驾驶舱 button
    log("click 🛠️ 驾驶舱");
    const cockpitBtn = page.locator('button:has-text("驾驶舱")').first();
    if (await cockpitBtn.isVisible().catch(() => false)) {
      await cockpitBtn.click();
      await page.waitForTimeout(800);
      await page.screenshot({ path: ts("02-cockpit-drawer"), fullPage: false });
      const drawerVisible = await page.locator('aside').first().isVisible().catch(() => false);
      result.steps.push({ name: "驾驶舱抽屉从右侧拉出 (aside visible)", ok: drawerVisible });
      const drawerIframeSrc = await page.locator('aside iframe').first().getAttribute('src').catch(() => "");
      result.steps.push({ name: "抽屉 iframe src 含 ?embed=drawer", ok: String(drawerIframeSrc || "").includes("embed=drawer"), detail: { src: drawerIframeSrc } });

      // close drawer
      log("close drawer via ✕");
      await page.locator('aside button[title*="关闭抽屉"]').first().click().catch(() => {});
      await page.waitForTimeout(400);
    } else {
      result.steps.push({ name: "驾驶舱抽屉从右侧拉出 (aside visible)", ok: false, detail: "驾驶舱按钮不可见" });
    }

    // click 公司层
    log("click 🏢 公司层");
    const companyBtn = page.locator('button:has-text("公司层")').first();
    if (await companyBtn.isVisible().catch(() => false)) {
      await companyBtn.click();
      await page.waitForTimeout(800);
      await page.screenshot({ path: ts("03-company-drawer"), fullPage: false });
      const drawerVisible = await page.locator('aside').first().isVisible().catch(() => false);
      result.steps.push({ name: "公司层抽屉从右侧拉出 (aside visible)", ok: drawerVisible });
    }

    // hide game
    log("click 🙈 隐藏游戏");
    const hideBtn = page.locator('button:has-text("隐藏游戏")').first();
    if (await hideBtn.isVisible().catch(() => false)) {
      await hideBtn.click();
      await page.waitForTimeout(400);
      await page.screenshot({ path: ts("04-game-hidden"), fullPage: false });
      const placeholderVisible = await page.locator('text=游戏已隐藏').first().isVisible().catch(() => false);
      result.steps.push({ name: "隐藏游戏后显示占位符", ok: placeholderVisible });
    }

    result.pass = result.steps.every((s) => s.ok);
  } catch (e) {
    result.error = String(e?.message || e);
    result.pass = false;
    try { await page.screenshot({ path: ts("99-error") }); } catch {}
  } finally {
    await browser.close();
  }

  for (const s of result.steps) log(`${s.ok ? "✓" : "✗"} ${s.name}${s.detail ? ` — ${JSON.stringify(s.detail)}` : ""}`);
  log(`整体: ${result.pass ? "✅ PASS" : "❌ FAIL"}`);
  fs.writeFileSync(path.join(OUT, `report-${Date.now()}.json`), JSON.stringify(result, null, 2));
  process.exit(result.pass ? 0 : 1);
})();
