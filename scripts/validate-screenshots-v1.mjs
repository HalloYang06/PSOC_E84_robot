// 第一版可用平台截图：登录 / 驾驶舱 / 工作台空 / 工作台双开瓷砖（含占用锁 badge）
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = process.env.API_BASE || "http://127.0.0.1:8010";
const WEB = process.env.WEB_BASE || "http://127.0.0.1:3100";
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "demo-pass";
const OUT_DIR = path.resolve("artifacts", "platform-screenshots-v1");
fs.mkdirSync(OUT_DIR, { recursive: true });

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
  console.log(`shot: ${file}`);
  return file;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1100 },
    locale: "zh-CN",
  });

  const token = await login(ctx);
  await ctx.addCookies([
    {
      name: "ai_collab_session",
      value: token,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
    },
  ]);

  const page = await ctx.newPage();
  await page.addInitScript((t) => {
    try {
      localStorage.setItem("ai_collab_token", t);
      localStorage.setItem("ai_collab_session", t);
    } catch (e) {}
    // Inject Authorization on all cross-origin fetch to 8010
    const origFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
      try {
        const url = typeof input === "string" ? input : input?.url || "";
        if (url.includes("127.0.0.1:8010") || url.includes("localhost:8010")) {
          const h = new Headers(init.headers || {});
          if (!h.has("Authorization")) h.set("Authorization", `Bearer ${t}`);
          return origFetch(input, { ...init, headers: h, credentials: "include" });
        }
      } catch (e) {}
      return origFetch(input, init);
    };
  }, token);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("[console.error]", msg.text());
  });

  console.log("→ login");
  await page.goto(`${WEB}/login`, { waitUntil: "networkidle" });
  await shoot(page, "01-login");

  await page.fill('input[type="email"], input[name="email"]', EMAIL).catch(() => {});
  await page.fill('input[type="password"], input[name="password"]', PASSWORD).catch(() => {});
  await page.click('button[type="submit"], button:has-text("登录"), button:has-text("Login")').catch(() => {});
  await page.waitForLoadState("networkidle").catch(() => {});

  console.log("→ projects list");
  await page.goto(`${WEB}/projects`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(2000);
  await shoot(page, "02-projects-list");

  console.log("→ cockpit");
  await page.goto(`${WEB}/projects/${PROJECT}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(3000);
  await shoot(page, "03-cockpit");

  console.log("→ workbench (empty)");
  await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(2500);
  await shoot(page, "04-workbench-empty");

  console.log("→ open all + buttons");
  // 尝试点左栏每个 NPC 行右侧的 "+" 打开瓷砖
  const plusButtons = page.locator('button[title="打开瓷砖"]');
  const count = await plusButtons.count();
  console.log(`found ${count} "+ open" buttons`);
  for (let i = 0; i < Math.min(count, 2); i++) {
    await plusButtons.nth(i).click().catch(() => {});
    await page.waitForTimeout(800);
  }
  await page.waitForTimeout(3500); // 等占用锁 badge & 消息流加载
  await shoot(page, "05-workbench-2-tiles-with-occupancy");

  // 收起档案，让消息流更显眼
  const collapseBtns = page.locator('button:has-text("收起档案")');
  const cc = await collapseBtns.count();
  for (let i = 0; i < cc; i++) {
    await collapseBtns.nth(i).click().catch(() => {});
    await page.waitForTimeout(300);
  }
  await page.waitForTimeout(1500);
  await shoot(page, "06-workbench-stream-focus");

  await ctx.close();
  await browser.close();
  console.log(`done. screenshots in ${OUT_DIR}`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
