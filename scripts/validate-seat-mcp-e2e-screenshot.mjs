// 截图证明：MCP e2e 之后真能在前端 NPC 瓷砖看到那些自主求助消息。
//
// 用法：先跑 validate-seat-mcp-e2e.py 灌入消息，再跑这个截图。
// 假设演示项目 proj_ai_collab，跨工位收件 NPC = 执行工位。

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const TARGET_NPC = process.env.TARGET_NPC || "执行工位"; // 跨工位 e2e 消息的收件人
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";

const OUT = path.resolve("artifacts", "mcp-e2e-2026-05-08");
fs.mkdirSync(OUT, { recursive: true });

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
  page.on("pageerror", (e) => console.error("PAGE-ERROR:", e.message));

  log(`打开工作台 → ${TARGET_NPC} 瓷砖`);
  await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}/workbench`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);

  await page.locator(`strong:text-is("${TARGET_NPC}")`).first().waitFor({ timeout: 8000 });
  const clicked = await page.evaluate((targetName) => {
    const strongs = Array.from(document.querySelectorAll('strong'));
    const target = strongs.find(s => s.textContent?.trim() === targetName);
    if (!target) return { ok: false };
    let actual = target.closest('li');
    if (actual && actual.querySelector('ul')) {
      const rows = Array.from(actual.querySelectorAll('li'));
      actual = rows.find(r => r.querySelector('strong')?.textContent?.trim() === targetName) || actual;
    }
    actual?.querySelector('button[title="打开瓷砖"]')?.click();
    return { ok: true };
  }, TARGET_NPC);
  if (!clicked.ok) {
    console.error(`找不到 NPC ${TARGET_NPC}`);
    await browser.close();
    process.exit(1);
  }
  await page.waitForTimeout(4000);
  await page.locator('button[title="手动刷新"]').first().click().catch(() => {});
  await page.waitForTimeout(3000);

  log("整张瓷砖截图");
  let p = path.join(OUT, "01-tile-full.png");
  await page.screenshot({ path: p, fullPage: true });

  log("聚焦消息流，给每条带 [e2e] 的消息加红框");
  await page.evaluate(() => {
    const msgs = Array.from(document.querySelectorAll('[data-role]'));
    for (const m of msgs) {
      if ((m.textContent || "").includes("[e2e]")) {
        m.style.outline = "3px solid red";
        m.style.outlineOffset = "2px";
      }
    }
  });
  await page.waitForTimeout(500);
  p = path.join(OUT, "02-tile-e2e-messages-highlighted.png");
  await page.screenshot({ path: p, fullPage: true });

  log("数一下 [e2e] 消息");
  const e2eCount = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[data-role]'))
      .filter(m => (m.textContent || "").includes("[e2e]")).length;
  });
  log(`  瓷砖里能看到的 [e2e] 消息条数 = ${e2eCount}`);

  log("dump 一下每条 [e2e] 消息的 role + 摘要");
  const e2eList = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[data-role]'))
      .filter(m => (m.textContent || "").includes("[e2e]"))
      .map(m => ({
        role: m.getAttribute('data-role'),
        text: (m.textContent || '').slice(0, 200).replace(/\s+/g, ' '),
      }));
  });
  for (const m of e2eList) {
    log(`  · role=${m.role}  text=${m.text}`);
  }

  await browser.close();

  // 输出一份 markdown 报告
  const md = [
    `# MCP 自主求助 e2e 截图`,
    ``,
    `- 时间：${new Date().toISOString()}`,
    `- 项目：${PROJECT}`,
    `- 目标 NPC（跨工位收件人）：${TARGET_NPC}`,
    `- 瓷砖里看到的 [e2e] 消息：**${e2eCount}** 条`,
    ``,
    `## 消息明细`,
    ``,
    ...e2eList.map((m, i) => `${i + 1}. **role=${m.role}** — ${m.text}`),
    ``,
    `## 截图`,
    ``,
    `- \`${path.join(OUT, "01-tile-full.png")}\``,
    `- \`${path.join(OUT, "02-tile-e2e-messages-highlighted.png")}\` （[e2e] 消息加红框）`,
  ].join("\n");
  const reportDir = path.resolve("docs", "screenshots", "v1");
  fs.mkdirSync(reportDir, { recursive: true });
  fs.writeFileSync(path.join(reportDir, "mcp-e2e-2026-05-08.md"), md);
  log(`报告：${path.join(reportDir, "mcp-e2e-2026-05-08.md")}`);
  process.exit(e2eCount >= 1 ? 0 : 1);
})();
