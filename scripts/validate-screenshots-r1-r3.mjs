import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = process.env.API_BASE || "http://127.0.0.1:8010";
const WEB = process.env.WEB_BASE || "http://127.0.0.1:3000";
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "demo-pass";
const STAMP = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
const OUT_DIR = path.resolve("artifacts", `validate-screenshots-${STAMP}`);
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

async function shoot(page, name, opts = {}) {
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: opts.fullPage ?? true });
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
  }, token);

  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("[console.error]", msg.text());
  });

  console.log("→ login page");
  await page.goto(`${WEB}/login`, { waitUntil: "networkidle" });
  await shoot(page, "01-login");

  await page.fill('input[type="email"], input[name="email"]', EMAIL).catch(() => {});
  await page.fill('input[type="password"], input[name="password"]', PASSWORD).catch(() => {});
  await page.click('button[type="submit"], button:has-text("登录"), button:has-text("Login")').catch(() => {});
  await page.waitForLoadState("networkidle").catch(() => {});

  console.log(`→ project cockpit /projects/${PROJECT}`);
  await page.goto(`${WEB}/projects/${PROJECT}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(2500);
  await shoot(page, "02-cockpit");

  console.log("→ workbench");
  await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(2500);
  await shoot(page, "03-workbench");

  await ctx.close();
  await browser.close();
  console.log(`done. screenshots in ${OUT_DIR}`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
