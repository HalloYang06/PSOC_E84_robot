// 全盘截图验收 — 用户使用视角
//
// 这个脚本做三件事：
//   1. 在演示项目里灌入 6 类消息（同工位、跨工位、自主合作、回执、待审、人工/系统）
//   2. 用 Playwright 走完用户主路径：登录 → 项目列表 → 游戏壳 → 驾驶舱抽屉 →
//      工作台（瓷砖打开看消息分色）→ 公司层抽屉 → 待审区 → 跨工位通道
//   3. 输出截图到 artifacts/full-walk-2026-05-08/ + 报告 docs/screenshots/v1/full-walk-2026-05-08.md
//
// 用法：
//   API_BASE=http://127.0.0.1:8010 WEB_BASE=http://127.0.0.1:3000 \
//   PROJECT_ID=proj_ai_collab \
//   node scripts/validate-full-walk-2026-05-08.mjs

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";

const OUT_DIR = path.resolve("artifacts", "full-walk-2026-05-08");
fs.mkdirSync(OUT_DIR, { recursive: true });

let stepIdx = 0;
function shotPath(name) {
  stepIdx += 1;
  const idx = String(stepIdx).padStart(2, "0");
  return path.join(OUT_DIR, `${idx}-${name}.png`);
}

const log = (m) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${m}`);

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

async function patchProfile(token, nodeId, body) {
  const r = await fetch(`${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/workstation-profiles/${encodeURIComponent(nodeId)}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`PATCH workstation-profile ${nodeId} HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function ensureLeads(token, project) {
  const seats = project.collaboration_config?.thread_workstations || [];
  const byNode = new Map();
  for (const s of seats) {
    const n = String(s.computer_node_id || "");
    if (!byNode.has(n)) byNode.set(n, []);
    byNode.get(n).push(s);
  }
  for (const [node, list] of byNode.entries()) {
    if (!node) continue;
    // 该工位的第一个 seat 设为 lead
    const lead = list[0];
    await patchProfile(token, node, { lead_seat_id: String(lead.id || lead.row_id) });
    log(`✓ 设置工位长：node=${node} lead=${lead.name}`);
  }
}

async function seedMessages(token, project) {
  const seats = project.collaboration_config?.thread_workstations || [];
  const sameNode = (() => {
    const byNode = new Map();
    for (const s of seats) {
      const n = String(s.computer_node_id || "");
      if (!byNode.has(n)) byNode.set(n, []);
      byNode.get(n).push(s);
    }
    for (const [, list] of byNode) if (list.length >= 2) return list;
    return null;
  })();
  if (!sameNode) throw new Error("种子前置：项目里需要 ≥2 个同工位 NPC");
  const [npcA, npcB] = sameNode;
  const npcCross = seats.find((s) => String(s.computer_node_id || "") !== String(npcA.computer_node_id || ""));
  if (!npcCross) throw new Error("种子前置：需要 ≥1 个跨工位 NPC");

  log(`同工位：${npcA.name} ↔ ${npcB.name}（node=${npcA.computer_node_id}）；跨工位：${npcCross.name}（node=${npcCross.computer_node_id}）`);

  const seeded = [];
  // 1) 人 → NPC B（人灰）
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "agent_command",
    title: "[人工演示] 用户直接派单给 NPC B",
    body: "请帮我把首页 nav 上加一个登出按钮，调 /api/auth/logout，跳回 /login。",
    sender_type: "human",
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "queued",
  }));
  // 2) 同工位 NPC A → NPC B（同工位绿）— sender_id 用 seat.id（前端 peerIds 用的就是 seat.id）
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[同工位演示] ${npcA.name} → ${npcB.name}`,
    body: `兄弟帮我看下 PR #42 的 React Hook 顺序，我怀疑触发了 react/no-conditional-hooks。`,
    sender_type: "agent",
    sender_id: String(npcA.id || npcA.row_id),
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "queued",
  }));
  // 3) 跨工位 NPC C → NPC B（跨工位紫，自动转工位长 + 强审）
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[跨工位演示] ${npcCross.name} → ${npcB.name}`,
    body: `后端 API /api/foo 增加了 paginate 参数，前端这边能不能跟一下？`,
    sender_type: "agent",
    sender_id: String(npcCross.id || npcCross.row_id),
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "queued",
  }));
  // 4) 自主合作 NPC A → NPC B (request_help 风格 body)
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[自主求助] reviewer`,
    body: `## 我（NPC \`${npcA.id}\`）的求助\n\n**找谁**：reviewer\n\n**问题**：\n请帮我看一下下面这段 SQL 是否会触发全表扫描。\n\n（本消息由 NPC 通过 seat-mcp \`request_help\` 工具自主发起。）`,
    sender_type: "agent",
    sender_id: String(npcA.id || npcA.row_id),
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "queued",
  }));
  // 5) 回执 — NPC B 自己回了一条
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "ai_reply",
    title: `[回执演示] ${npcB.name} 完成上一条`,
    body: `已修：apps/web/components/Header.tsx 加了登出按钮；调用 /api/auth/logout；跳 /login。\n\n- 修改 Header.tsx：加登出按钮 — https://github.com/wenjunyong666/ai-/blob/ai/game-loop-core/apps/web/components/Header.tsx`,
    sender_type: "agent",
    sender_id: String(npcB.id || npcB.row_id),
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "completed",
  }));
  // 6) 系统/CLI watcher 噪声
  seeded.push(await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[系统] watcher 启动`,
    body: `watcher 启动 ok（provider=claude, cwd=D:/ai合作产品）。\nmcp 加载: seat-mcp, claude-bridge.\nheartbeat 心跳建立。`,
    sender_type: "system",
    recipient_type: "thread_workstation",
    recipient_id: String(npcB.id || npcB.row_id),
    status: "completed",
  }));
  log(`✓ 灌入 ${seeded.length} 条种子消息`);
  return { npcA, npcB, npcCross, seeded };
}

async function main() {
  const result = { started_at: new Date().toISOString(), pass: false, steps: [], shots: [] };

  log("登录平台");
  const token = await login();
  log("拉项目配置");
  const project = await getProject(token);
  log("确保每个工位都有工位长");
  await ensureLeads(token, project);
  // 重新拉一次（profile 可能变了）
  const projectAfter = await getProject(token);
  log("灌入 6 类种子消息");
  const { npcA, npcB, npcCross, seeded } = await seedMessages(token, projectAfter);

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const cookieDomain = new URL(WEB).hostname;
  await ctx.addCookies([
    { name: "farm_access_token", value: token, domain: cookieDomain, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
    { name: "farm_user", value: JSON.stringify({ id: "lead", name: "lead", email: EMAIL }), domain: cookieDomain, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
  ]);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("PAGE-ERROR:", e.message));

  try {
    // ==== A 登录页 ====
    log("A 登录页截图（先 logout 再开 /login）");
    await page.goto(`${WEB}/login`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(700);
    let p = shotPath("login-page");
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);
    result.steps.push({ name: "A 登录页", ok: true });

    // 重新加 cookie 进项目
    await ctx.addCookies([
      { name: "farm_access_token", value: token, domain: cookieDomain, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
    ]);

    // ==== B 项目列表 ====
    log("B 项目列表");
    await page.goto(`${WEB}/projects`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(800);
    p = shotPath("projects-list");
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);
    result.steps.push({ name: "B 项目列表", ok: true });

    // ==== C 游戏壳（默认进入 /projects/[id]）====
    log("C 游戏壳");
    await page.goto(`${WEB}/projects/${encodeURIComponent(PROJECT)}`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(1500);
    p = shotPath("game-shell");
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);
    const topNavOk = await page.locator('button:has-text("驾驶舱")').first().isVisible().catch(() => false);
    result.steps.push({ name: "C 游戏壳 + 顶部薄 nav 显示", ok: topNavOk });

    // ==== D 驾驶舱抽屉 ====
    log("D 驾驶舱抽屉");
    await page.locator('button:has-text("驾驶舱")').first().click().catch(() => {});
    await page.waitForTimeout(1500);
    p = shotPath("cockpit-drawer");
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);
    const drawerVisible = await page.locator('aside').first().isVisible().catch(() => false);
    result.steps.push({ name: "D 驾驶舱抽屉 70vw 拉出", ok: drawerVisible });
    // 关抽屉
    await page.locator('aside button[title*="关闭"]').first().click().catch(() => {});
    await page.waitForTimeout(500);

    // ==== E 工位长会议室 ====
    log("E 公司层抽屉");
    await page.locator('button:has-text("公司层")').first().click().catch(() => {});
    await page.waitForTimeout(1500);
    p = shotPath("company-drawer");
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);
    result.steps.push({ name: "E 公司层抽屉打开", ok: await page.locator('aside').first().isVisible().catch(() => false) });
    await page.locator('aside button[title*="关闭"]').first().click().catch(() => {});
    await page.waitForTimeout(500);

    // ==== F 工作台（直接打开独立路由，便于截图）====
    log("F 工作台 - 全景");
    const wbUrl = `${WEB}/projects/${encodeURIComponent(PROJECT)}/workbench`;
    await page.goto(wbUrl, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(1800);
    p = shotPath("workbench-overview");
    await page.screenshot({ path: p, fullPage: true });
    result.shots.push(p);
    const wsGroupOk = await page.locator('text=/前端工位|执行工位/').first().isVisible().catch(() => false);
    result.steps.push({ name: "F 工作台左栏按工位分组", ok: wsGroupOk });

    // ==== G 打开 NPC B 瓷砖 ====
    log(`G 打开 ${npcB.name} 瓷砖`);
    // 用 evaluate ascend：找到名字 strong → closest npcRow（跳过外层 group li）→ click button
    await page.locator(`strong:text-is("${npcB.name}")`).first().waitFor({ timeout: 8000 });
    const clickResult = await page.evaluate((targetName) => {
      const strongs = Array.from(document.querySelectorAll('strong'));
      const target = strongs.find(s => s.textContent?.trim() === targetName);
      if (!target) return { ok: false, why: 'name strong not found' };
      let actual = target.closest('li');
      if (actual && actual.querySelector('ul')) {
        const rows = Array.from(actual.querySelectorAll('li'));
        actual = rows.find(r => r.querySelector('strong')?.textContent?.trim() === targetName) || actual;
      }
      const btn = actual?.querySelector('button[title="打开瓷砖"]');
      if (!btn) return { ok: false, why: 'no open button' };
      btn.click();
      return { ok: true };
    }, npcB.name);
    if (!clickResult.ok) log(`  ! 打开瓷砖失败：${clickResult.why}`);
    await page.waitForTimeout(4500);
    // 强制刷一次消息流
    await page.locator('button[title="手动刷新"]').first().click().catch(() => {});
    await page.waitForTimeout(2500);
    p = shotPath("tile-opened");
    await page.screenshot({ path: p, fullPage: true });
    result.shots.push(p);
    const dispatchBtnOk = (await page.locator("button", { hasText: "→ 派" }).count()) >= 1;
    // 队列卡用 "📥 需求 N" / "📋 任务 N" / "📤 我派的" 三 tab；任一存在即认为队列卡渲染了
    const queueOk = (await page.locator('button[title*="需求队列"]').count()) >= 1
      || (await page.locator('button[title*="任务队列"]').count()) >= 1
      || (await page.getByText(/📥\s*需求/).count()) >= 1;
    result.steps.push({ name: "G NPC 瓷砖：→派 按钮存在", ok: dispatchBtnOk });
    result.steps.push({ name: "G NPC 瓷砖：任务队列卡显示", ok: queueOk });

    // ==== H 6 色消息流（统计 data-role 多样性）====
    log("H 消息流分色");
    const roleCounts = {};
    for (const role of ["human", "self", "peer", "external", "watcher", "system"]) {
      roleCounts[role] = await page.locator(`[data-role="${role}"]`).count();
    }
    log(`  data-role 分布：${JSON.stringify(roleCounts)}`);
    p = shotPath("message-stream-colors");
    await page.screenshot({ path: p, fullPage: true });
    result.shots.push(p);
    const seenRoles = Object.entries(roleCounts).filter(([, c]) => c > 0).length;
    result.steps.push({ name: `H 消息流出现 ≥3 种 role 着色（实际 ${seenRoles}）`, ok: seenRoles >= 3, detail: roleCounts });
    result.steps.push({ name: "H 同工位 (peer) 消息能命中绿色", ok: roleCounts.peer > 0, detail: { peer: roleCounts.peer } });

    // ==== I 跨工位通道（紫色 section）====
    log("I 跨工位通道 section");
    const crossSection = await page.locator('text=跨工位通道').first().isVisible().catch(() => false);
    result.steps.push({ name: "I 跨工位通道 section 出现", ok: crossSection });

    // ==== J 同工位伙伴 chip + → 派 ====
    log("J 同工位伙伴 chip");
    p = shotPath("teammates-chips");
    await page.locator('h3:has-text("同工位伙伴"), text=同工位伙伴').first().scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(400);
    await page.screenshot({ path: p, fullPage: false });
    result.shots.push(p);

    // ==== K 公司层独立路由 ====
    log("K 公司层独立路由");
    const compUrl = `${WEB}/projects/${encodeURIComponent(PROJECT)}/company`;
    await page.goto(compUrl, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    p = shotPath("company-page");
    await page.screenshot({ path: p, fullPage: true });
    result.shots.push(p);
    result.steps.push({ name: "K 公司层独立路由可达", ok: !page.url().includes("/login") });

    result.pass = result.steps.every((s) => s.ok);
  } catch (e) {
    result.error = String(e?.message || e);
    log(`错误：${result.error}`);
    try { await page.screenshot({ path: shotPath("error") }); } catch {}
  } finally {
    await browser.close();
  }

  result.finished_at = new Date().toISOString();
  result.npcs = { same: [npcA?.name, npcB?.name], cross: [npcCross?.name] };
  result.seeded_count = seeded?.length || 0;

  for (const s of result.steps) log(`${s.ok ? "✓" : "✗"} ${s.name}${s.detail ? ` — ${JSON.stringify(s.detail)}` : ""}`);
  log(`整体: ${result.pass ? "PASS" : "FAIL"}`);

  fs.writeFileSync(path.join(OUT_DIR, `report.json`), JSON.stringify(result, null, 2));
  const md = [
    `# 全盘截图验收报告（用户使用视角）`,
    ``,
    `- 时间：${result.started_at} → ${result.finished_at}`,
    `- 项目：${PROJECT}`,
    `- 同工位 NPC：${(result.npcs?.same || []).join(", ")}`,
    `- 跨工位 NPC：${(result.npcs?.cross || []).join(", ")}`,
    `- 灌入演示消息：${result.seeded_count} 条`,
    `- 整体：${result.pass ? "PASS" : "FAIL"}`,
    ``,
    `## 步骤断言`,
    ``,
    ...result.steps.map((s) => `- ${s.ok ? "✓" : "✗"} **${s.name}**${s.detail ? ` — \`${JSON.stringify(s.detail)}\`` : ""}`),
    ``,
    `## 截图`,
    ``,
    ...result.shots.map((sp) => `- \`${sp}\``),
  ].join("\n");
  const reportDir = path.resolve("docs", "screenshots", "v1");
  fs.mkdirSync(reportDir, { recursive: true });
  fs.writeFileSync(path.join(reportDir, "full-walk-2026-05-08.md"), md);
  console.log(`\n报告：${path.join(reportDir, "full-walk-2026-05-08.md")}`);
  process.exit(result.pass ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
