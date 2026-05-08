// validate-tile-ui-2026-05-08.mjs
// Step0/Step2/Step3 截图验收：
//   - 同工位伙伴 chip 上有"→ 派"按钮
//   - 我的任务队列卡（若 inbox 有 queued 消息）
//   - 消息流分色（同工位绿 / 跨工位紫 / 系统红 / 人灰）
//
// 用法：
//   WEB_BASE=http://127.0.0.1:3000 node scripts/validate-tile-ui-2026-05-08.mjs

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT_DIR = path.resolve("artifacts", "tile-ui-2026-05-08");
fs.mkdirSync(OUT_DIR, { recursive: true });

async function login() {
  const r = await fetch(`${API}/api/auth/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!r.ok) throw new Error(`login HTTP ${r.status}: ${await r.text()}`);
  return (await r.json()).data.access_token;
}

async function getProject(token) {
  const r = await fetch(`${API}/api/projects/${encodeURIComponent(PROJECT)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`get project HTTP ${r.status}: ${await r.text()}`);
  return (await r.json()).data;
}

async function postMessage(token, payload) {
  const r = await fetch(`${API}/api/collaboration/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`POST /messages HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function main() {
  const result = { started_at: new Date().toISOString(), pass: false, steps: [], shots: [] };
  const log = (m) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${m}`);

  const token = await login();
  log("✓ login");
  const project = await getProject(token);
  const seats = project.collaboration_config?.thread_workstations || [];
  const sameWs = (() => {
    const byNode = new Map();
    for (const s of seats) {
      const n = String(s.computer_node_id || "");
      if (!byNode.has(n)) byNode.set(n, []);
      byNode.get(n).push(s);
    }
    for (const [n, list] of byNode.entries()) if (n && list.length >= 2) return list;
    return null;
  })();
  if (!sameWs) throw new Error("没找到 ≥2 个同工位 seat");
  const [npcA, npcB] = sameWs;
  log(`✓ 同工位 NPC: ${npcA.name} + ${npcB.name}`);

  // 提前用 Step1 后端给 npcB 制造一条 queued 消息（来自 npcA）+ 一条人工消息（来自 human）→ 让任务队列卡和分色都有数据
  const seedAgent = await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[同工位演示] ${npcA.name} → ${npcB.name}`,
    body: `请协助审核以下内容（演示同工位互派）。`,
    sender_type: "agent",
    sender_id: String(npcA.row_id || npcA.id),
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.row_id || npcB.id),
    status: "queued",
  });
  log(`✓ seed agent→agent: ${seedAgent.id} status=${seedAgent.status}`);

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const cookieDomain = new URL(WEB).hostname;
  await ctx.addCookies([
    { name: "farm_access_token", value: token, domain: cookieDomain, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
    { name: "farm_user", value: JSON.stringify({ id: "lead", name: "lead", email: EMAIL }), domain: cookieDomain, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
  ]);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("PAGE-ERROR:", e.message));

  // 进 workbench
  const wbUrl = `${WEB}/projects/${encodeURIComponent(PROJECT)}/workbench`;
  await page.goto(wbUrl, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(1500);
  if (page.url().includes("/login")) throw new Error(`跳到 login 了：${page.url()} — cookie 注入未生效`);
  log(`✓ workbench loaded: ${page.url()}`);
  const wbShot = path.join(OUT_DIR, "01-workbench.png");
  await page.screenshot({ path: wbShot, fullPage: true });
  result.shots.push(wbShot);

  // 找到 npcB 的 + 号点开
  // workbench 左栏每个 NPC 行有个 button[title="打开瓷砖"] 旁边显示 NPC 名
  await page.waitForSelector('button[title="打开瓷砖"]', { timeout: 10000 });
  // 找含 npcB 名字的 li 里的 + 按钮
  const liNpcB = page.locator(`li:has-text("${npcB.name}")`).first();
  try {
    const opener = liNpcB.locator('button[title="打开瓷砖"]').first();
    await opener.click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    log(`✓ 点开了 ${npcB.name} 瓷砖`);
  } catch (e) {
    log(`点 npcB 瓷砖失败：${e instanceof Error ? e.message : e}`);
  }
  const tile1Shot = path.join(OUT_DIR, "02-tile-opened.png");
  await page.screenshot({ path: tile1Shot, fullPage: true });
  result.shots.push(tile1Shot);
  log(`✓ 截图瓷砖打开后: ${tile1Shot}`);

  // 找有没有"→ 派"按钮文本（peerDispatchBtn）
  const dispatchBtnCount = await page.locator("button", { hasText: "→ 派" }).count();
  // 任务队列：tabs 区有"📥 需求"或"📋 任务"按钮（瓷砖双队列已升级 — 老文案"我的任务队列"已被 tabs 替代）
  const queueExists = await page.locator("button", { hasText: /📥 需求|📋 任务/ }).count();
  // 分色：找消息流里的 .role_peer / .role_external 元素（CSS module hash 后名字会变，用 inline data-role 兜底）
  const peerColored = await page.locator('[data-role="peer"], [data-role="external"], [data-role="human"]').count();

  result.steps.push({ name: "→派 按钮存在", ok: dispatchBtnCount >= 1, detail: { count: dispatchBtnCount } });
  result.steps.push({ name: "任务队列卡显示", ok: queueExists >= 1, detail: { count: queueExists } });
  result.steps.push({ name: "消息分色 data-role 存在", ok: peerColored >= 1, detail: { count: peerColored } });

  result.pass = result.steps.every((s) => s.ok);
  log(`整体: ${result.pass ? "✅ PASS" : "❌ FAIL"}`);
  for (const s of result.steps) log(`${s.ok ? "✓" : "✗"} ${s.name} — ${JSON.stringify(s.detail)}`);

  await browser.close();

  result.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(OUT_DIR, `report.json`), JSON.stringify(result, null, 2));
  const md = [
    `# Step0/2/3 NpcTile UI 截图验收`,
    ``,
    `- 时间：${result.started_at} → ${result.finished_at}`,
    `- 整体：${result.pass ? "✅ PASS" : "❌ FAIL"}`,
    ``,
    `## 步骤`,
    "",
    ...result.steps.map((s) => `- ${s.ok ? "✓" : "✗"} **${s.name}** — \`${JSON.stringify(s.detail)}\``),
    ``,
    `## 截图`,
    "",
    ...result.shots.map((p) => `- \`${p}\``),
  ].join("\n");
  const mdPath = path.resolve("docs", "screenshots", "v1", `tile-ui-2026-05-08.md`);
  fs.writeFileSync(mdPath, md);
  console.log(`\n报告：${mdPath}`);
  process.exit(result.pass ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
