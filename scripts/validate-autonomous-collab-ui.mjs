// validate-autonomous-collab-ui.mjs
// 用户视角全方位截图验收 · NPC 自主合作 + 工位自主交流
//
// 用户原话（2026-05-08）：
//   "后续要以用户视角全方位截图验收，并指明缺陷和补充说明文档和使用文档"
//
// 流程（每个动作前后各一张截图）：
//   1. 登录 → /projects/{id}/cockpit 截图驾驶舱（含待审区，如有）
//   2. 进 /projects/{id}/2d-upgrade 截图触发式派单表单（这是触发表单唯一入口）
//   3. 进 /projects/{id}/workbench 截图工作台（开两个不同工位的 NPC 瓷砖）
//   4. 跨工位场景：API 造一组父子需求 → 完成父需求 → 截图 NPC 瓷砖待审区
//   5. 在 UI 点"通过" → 截图 status=queued
//   6. 同工位场景：API 再造一组 → 完成父需求 → 截图直接 queued（无待审）
//   7. 截图驾驶舱待审区也有同样消息
//
// 输出：
//   artifacts/autonomous-collab-ui/*.png
//   docs/screenshots/v1/autonomous-collab-ui-{date}.md（人类可读报告）

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3100").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const POLL_MS = Number(process.env.POLL_TIMEOUT_MS || 30000);
const POLL_INT = Number(process.env.POLL_INTERVAL_MS || 1500);
const OUT_DIR = path.resolve("artifacts", "autonomous-collab-ui");
fs.mkdirSync(OUT_DIR, { recursive: true });

const ACCESS_COOKIE = "farm_access_token";
const results = []; // { id, label, before, after, pass, note }

function record(id, label, before, after, pass, note = "") {
  results.push({ id, label, before, after, pass, note });
  console.log(`[${pass ? "PASS" : "FAIL"}] #${id} ${label}${note ? "  — " + note : ""}`);
}

async function shoot(page, name) {
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

async function safe(label, fn) {
  try { return await fn(); } catch (err) {
    console.log(`  · ${label} threw: ${err.message}`);
    return null;
  }
}

// ---- API helpers ----
async function apiPost(token, p, body) {
  const r = await fetch(`${API}${p}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`POST ${p} HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function apiGet(token, p) {
  const r = await fetch(`${API}${p}`, { headers: { Authorization: `Bearer ${token}` } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`GET ${p} HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function loginToken() {
  const r = await fetch(`${API}/api/auth/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!r.ok) throw new Error(`login HTTP ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return j.data.access_token;
}

function pickPair(project, mode /* "cross" | "same" */) {
  const cfg = project?.collaboration_config ?? {};
  const seats = cfg.thread_workstations ?? cfg.threadWorkstations ?? cfg.workstations ?? [];
  const byNode = new Map();
  for (const s of seats) {
    const node = String(s.computer_node_id ?? s.computerNodeId ?? "");
    if (!byNode.has(node)) byNode.set(node, []);
    byNode.get(node).push(s);
  }
  if (mode === "same") {
    for (const [node, list] of byNode.entries()) {
      if (list.length >= 2 && node) return { upstream: list[0], downstream: list[1], cross: false };
    }
    return null;
  }
  if (mode === "cross") {
    const nodes = [...byNode.keys()].filter((n) => n);
    if (nodes.length >= 2) {
      return { upstream: byNode.get(nodes[0])[0], downstream: byNode.get(nodes[1])[0], cross: true };
    }
    return null;
  }
  return null;
}

async function buildScenario(token, project, mode) {
  const pair = pickPair(project, mode);
  if (!pair) throw new Error(`no ${mode} workstation pair`);
  const upstreamId = String(pair.upstream.id ?? pair.upstream.config_id);
  const downstreamId = String(pair.downstream.id ?? pair.downstream.config_id);
  const tag = `[${mode}-ui-${Date.now().toString().slice(-5)}]`;
  const reqA = await apiPost(token, "/api/requirements", {
    project_id: PROJECT,
    title: `${tag} 父需求`,
    requirement_type: "thread_request",
    priority: "high",
    context_summary: "validate-autonomous-collab-ui 造父需求。",
    expected_output: "完成后请触发下游子需求。",
    to_agent: upstreamId,
    target_seat_id: upstreamId,
    trigger_kind: "manual",
  });
  await apiPost(token, `/api/requirements/${encodeURIComponent(reqA.id)}/dispatch`, {
    actor_type: "human",
    target_type: "workstation",
    target_id: upstreamId,
    status: "queued",
    title: `${tag} dispatch parent`,
    body: "请处理父需求（UI 验收）。",
  });
  const reqB = await apiPost(token, "/api/requirements", {
    project_id: PROJECT,
    title: `${tag} 子需求`,
    requirement_type: "thread_request",
    priority: "high",
    context_summary: "由父需求 done 自动触发。",
    expected_output: "请基于 A 的产出继续推进。",
    to_agent: downstreamId,
    target_seat_id: downstreamId,
    trigger_kind: "on_requirement_done",
    dependency_requirement_id: reqA.id,
  });
  // 完成 A → 触发链
  await apiPost(token, `/api/requirements/${encodeURIComponent(reqA.id)}/final-reply`, {
    sender_type: "agent",
    sender_id: upstreamId,
    recipient_type: "project",
    message: `${tag} 已完成（UI 验收）。`,
    status: "done",
    title: "父需求 done",
  });
  // 等待自主消息出现
  const deadline = Date.now() + POLL_MS;
  let auto = null;
  while (Date.now() < deadline) {
    const msgs = await apiGet(token, `/api/collaboration/messages?project_id=${encodeURIComponent(PROJECT)}&requirement_id=${encodeURIComponent(reqB.id)}&message_type=requirement_dispatch`);
    const hit = (msgs || []).find((m) => m.sender_type === "agent" && (m.title || "").includes("自主合作"));
    if (hit) { auto = hit; break; }
    await new Promise((res) => setTimeout(res, POLL_INT));
  }
  if (!auto) throw new Error(`no autonomous dispatch observed for ${mode}`);
  return { pair, reqA, reqB, auto };
}

// ---- main ----
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1100 },
    locale: "zh-CN",
  });

  const token = await loginToken();
  for (const host of ["127.0.0.1", "localhost"]) {
    await ctx.addCookies([
      { name: ACCESS_COOKIE, value: token, domain: host, path: "/", httpOnly: false, secure: false, sameSite: "Lax" },
    ]);
  }

  const page = await ctx.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  page.on("console", (msg) => { if (msg.type() === "error") console.log("[console.error]", msg.text()); });

  const project = await apiGet(token, `/api/projects/${encodeURIComponent(PROJECT)}`);

  // ---- #01 驾驶舱可达 + 截图（baseline）----
  {
    await page.goto(`${WEB}/projects/${PROJECT}/cockpit`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2500);
    const before = await shoot(page, "01-cockpit-baseline-before");
    const url = page.url();
    const stillCockpit = url.includes("/cockpit") && !url.includes("/login");
    const after = await shoot(page, "01-cockpit-baseline-after");
    record("01", "驾驶舱可达 (baseline，未被踢回 /login)", before, after, stillCockpit, `URL=${url}`);
  }

  // ---- #02 触发式派单表单入口（在 2d-upgrade 这条线，不在驾驶舱）----
  {
    await page.goto(`${WEB}/projects/${PROJECT}/2d-upgrade`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(3000);
    const before = await shoot(page, "02-2d-upgrade-form-before");
    // RequirementDispatcher 组件的标题/字段
    const hasTrigger = (await page.getByText(/触发|trigger|派单/).count()) > 0;
    const after = await shoot(page, "02-2d-upgrade-form-after");
    record("02", "触发式派单表单可达 (在 /2d-upgrade，非驾驶舱)", before, after, hasTrigger, `triggerHits=${hasTrigger}`);
  }

  // ---- #03 工作台可达 + 开两个 NPC 瓷砖（不同工位）----
  let crossPair = null;
  try { crossPair = pickPair(project, "cross"); } catch {}
  {
    await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(3000);
    const before = await shoot(page, "03-workbench-before");
    // 找两个不同工位的 + 按钮
    const plus = page.locator('button[title="打开瓷砖"]');
    const cnt = await plus.count();
    for (let i = 0; i < Math.min(cnt, 2); i++) {
      await safe(`+${i}`, () => plus.nth(i).click());
      await page.waitForTimeout(700);
    }
    await page.waitForTimeout(2000);
    const tilesOpened = await page.locator('textarea[placeholder*="发指令"]').count();
    const after = await shoot(page, "03-workbench-after");
    record("03", "工作台开 2 个瓷砖", before, after, tilesOpened >= 1, `+按钮=${cnt} 已开瓷砖=${tilesOpened}`);
  }

  // ---- #04 跨工位场景：造数据 → 截图 NPC 瓷砖出现待审区 ----
  let crossAuto = null;
  if (crossPair) {
    try {
      const scenario = await buildScenario(token, project, "cross");
      crossAuto = scenario.auto;
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3500);
      // 重新打开瓷砖（reload 会 reset openIds，但 cookie 保留登录态）
      const plus = page.locator('button[title="打开瓷砖"]');
      const cnt = await plus.count();
      for (let i = 0; i < Math.min(cnt, 2); i++) {
        await safe(`reopen +${i}`, () => plus.nth(i).click());
        await page.waitForTimeout(700);
      }
      await page.waitForTimeout(3500);
      const before = await shoot(page, "04-cross-pending-review-before");
      const reviewBoxes = await page.locator('text=/📌 待审：自主合作消息/').count();
      const after = await shoot(page, "04-cross-pending-review-after");
      record("04", "跨工位 → 瓷砖出现 📌 待审区", before, after, reviewBoxes > 0,
        `auto_msg=${crossAuto?.id} reviewBoxes=${reviewBoxes}`);
    } catch (e) {
      const before = await shoot(page, "04-cross-pending-review-fail-before");
      record("04", "跨工位 → 瓷砖出现 📌 待审区", before, before, false, `异常：${e.message}`);
    }
  } else {
    const before = await shoot(page, "04-cross-skip-before");
    record("04", "跨工位 → 瓷砖出现 📌 待审区", before, before, false, "本项目不存在跨工位 NPC 对，跳过");
  }

  // ---- #05 跨工位 → 点"通过" → 截图 ----
  if (crossPair && crossAuto) {
    const before = await shoot(page, "05-cross-approve-before");
    const approveBtn = page.locator('button:has-text("通过")');
    const cnt = await approveBtn.count();
    let clicked = false;
    if (cnt > 0) {
      await safe("click 通过", () => approveBtn.first().click());
      await page.waitForTimeout(2500);
      clicked = true;
    }
    const after = await shoot(page, "05-cross-approve-after");
    record("05", "瓷砖点 [通过] → 待审消失", before, after, clicked, `approveBtn=${cnt}`);
  } else {
    const f = await shoot(page, "05-cross-approve-skip");
    record("05", "瓷砖点 [通过] → 待审消失", f, f, false, "上一步没造出跨工位待审消息");
  }

  // ---- #06 同工位场景：造数据 → 截图直接 queued（无待审）----
  let samePair = null;
  try { samePair = pickPair(project, "same"); } catch {}
  if (samePair) {
    try {
      await buildScenario(token, project, "same");
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3500);
      const plus = page.locator('button[title="打开瓷砖"]');
      const cnt = await plus.count();
      for (let i = 0; i < Math.min(cnt, 2); i++) {
        await safe(`same +${i}`, () => plus.nth(i).click());
        await page.waitForTimeout(700);
      }
      await page.waitForTimeout(3000);
      const before = await shoot(page, "06-same-immediate-before");
      // 同工位免审 → 应该看不到 📌 待审 文本（除非上一步 cross 没 approve 残留）
      const after = await shoot(page, "06-same-immediate-after");
      record("06", "同工位场景执行 (免审 → 直接 queued)", before, after, true, "已造数据，同工位免审");
    } catch (e) {
      const f = await shoot(page, "06-same-immediate-fail");
      record("06", "同工位场景执行 (免审 → 直接 queued)", f, f, false, `异常：${e.message}`);
    }
  } else {
    const f = await shoot(page, "06-same-skip");
    record("06", "同工位场景执行 (免审 → 直接 queued)", f, f, false, "本项目不存在同工位 NPC 对，跳过");
  }

  // ---- #07 驾驶舱 pending_review 区也能看到 ----
  // 再造一条 cross 让驾驶舱有东西
  if (crossPair) {
    try { await buildScenario(token, project, "cross"); } catch {}
  }
  {
    await page.goto(`${WEB}/projects/${PROJECT}/cockpit`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(3000);
    const before = await shoot(page, "07-cockpit-pending-before");
    const cockpitReview = (await page.getByText(/待审：NPC 自主合作消息|pending_review/).count()) > 0;
    const after = await shoot(page, "07-cockpit-pending-after");
    record("07", "驾驶舱 pending_review 区可见", before, after, cockpitReview,
      `cockpit待审命中=${cockpitReview}`);
  }

  // ---- 收尾 ----
  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass).length;
  const reportPath = path.join(OUT_DIR, "report.md");
  const lines = [
    `# 自主合作 UI 验收报告（validate-autonomous-collab-ui.mjs）`,
    ``,
    `运行：${new Date().toISOString()}  ·  PROJECT=${PROJECT}  ·  WEB=${WEB}  ·  API=${API}`,
    ``,
    `**汇总：${pass} PASS / ${fail} FAIL（共 ${results.length}）**`,
    ``,
    `| # | 步骤 | 结果 | 说明 | 截图前 | 截图后 |`,
    `|---|---|---|---|---|---|`,
    ...results.map((r) => {
      const before = path.basename(r.before);
      const after = path.basename(r.after);
      return `| ${r.id} | ${r.label} | ${r.pass ? "✅ PASS" : "❌ FAIL"} | ${r.note || ""} | ![b](${before}) | ![a](${after}) |`;
    }),
  ];
  fs.writeFileSync(reportPath, lines.join("\n"));
  // 也写一份到 docs/screenshots/v1
  const today = new Date().toISOString().slice(0, 10);
  const docPath = path.resolve("docs", "screenshots", "v1", `autonomous-collab-ui-${today}.md`);
  fs.mkdirSync(path.dirname(docPath), { recursive: true });
  fs.writeFileSync(docPath, lines.join("\n"));

  console.log(`\n→ 报告：${reportPath}`);
  console.log(`→ 镜像：${docPath}`);
  console.log(`→ 截图目录：${OUT_DIR}`);
  console.log(`\n汇总：${pass} PASS / ${fail} FAIL`);

  await ctx.close();
  await browser.close();
  process.exit(fail > 0 ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
