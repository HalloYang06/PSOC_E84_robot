#!/usr/bin/env node
// 真验收 A — 真 AI 出回执 + Playwright 截图瓷砖看见全链
//
// 链路：
//   1. 跨工位派单：执行工位 → 前端工位-副（非 lead）
//   2. 后端兜底 redirect 到 wsB.lead = 前端工位
//   3. approve（人工审核）
//   4. 工位长 ack 回执 → 直返 sender
//   5. 工位长内派给 前端工位-副（同工位 queued）
//   6. **真调 claude -p** 让它生成 markdown done 回执（这是真 AI）
//   7. done 回执直返原 sender = 执行工位
//   8. Playwright 打开 sender 工作台瓷砖 → 截图断言能看见 ack + done（含 AI 真 markdown）
//
// 用法：node scripts/validate-real-final-purpose.mjs
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright";

const API = process.env.API_BASE || "http://127.0.0.1:8010";
const WEB = process.env.WEB_BASE || "http://127.0.0.1:3100";
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";

const STAMP = new Date().toISOString().replace(/[:.]/g, "-");
const OUT_DIR = join(process.cwd(), "artifacts", "real-final-purpose", STAMP);
mkdirSync(OUT_DIR, { recursive: true });

const log = (...a) => console.log(`[${new Date().toLocaleTimeString()}]`, ...a);
const events = [];
const record = (name, ok, detail) => {
  events.push({ name, ok, detail });
  log(`${ok ? "✓" : "✗"} ${name}`, detail !== undefined ? JSON.stringify(detail).slice(0, 200) : "");
};

async function api(method, path, token, body) {
  const headers = { "Content-Type": "application/json", Connection: "close" };
  if (token) headers.Authorization = `Bearer ${token}`;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const res = await fetch(`${API}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      const text = await res.text();
      let parsed;
      try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = { _raw: text }; }
      return { status: res.status, body: parsed };
    } catch (e) {
      if (attempt === 3) throw e;
      log(`  fetch retry ${attempt}/3: ${e.message}`);
      await new Promise((r) => setTimeout(r, 300 * attempt));
    }
  }
}

async function realAiDoneBody(prompt) {
  // 用 claude -p 非交互出 markdown（Windows 上 npm 全局 .cmd 必须 shell:true）
  log("→ 调真 claude -p ...");
  const t0 = Date.now();
  const r = spawnSync("claude -p --dangerously-skip-permissions", {
    input: prompt,
    encoding: "utf-8",
    maxBuffer: 4 * 1024 * 1024,
    timeout: 120_000,
    shell: true,
  });
  const elapsed = Date.now() - t0;
  if (r.status !== 0) {
    log("✗ claude 调用失败", { code: r.status, signal: r.signal, stderr: (r.stderr || "").slice(0, 300), error: r.error?.message });
    return { ok: false, body: "", elapsed };
  }
  const out = (r.stdout || "").trim();
  log(`✓ claude 真回了 ${out.length} 字符（${elapsed}ms）`);
  return { ok: true, body: out, elapsed };
}

(async () => {
  const login = await api("POST", "/api/auth/session", null, { email: EMAIL, password: PASSWORD });
  const token = login.body?.data?.access_token;
  record("登录", !!token, { status: login.status });
  if (!token) process.exit(1);

  // 拿工位 + 工位下的 seats（DB 主键）
  const ws = (await api("GET", `/api/projects/${PROJECT}/workstations`, token)).body?.data || [];
  const wsWithSeats = [];
  for (const w of ws) {
    const s = (await api("GET", `/api/projects/${PROJECT}/workstations/${w.id}/seats`, token)).body?.data || [];
    if (s.length > 0) wsWithSeats.push({ ...w, seats: s });
  }
  if (wsWithSeats.length < 2) {
    record("两工位均含 NPC", false, { wsCount: wsWithSeats.length });
    process.exit(1);
  }
  const wsA = wsWithSeats[0]; // sender side
  const wsB = wsWithSeats[1]; // 跨工位接收 + lead 转手
  const sender = wsA.seats[0];
  const leadSeat = wsB.seats[0];
  const executor = wsB.seats[1] || wsB.seats[0];
  record("挑选 sender / lead / executor", true, {
    sender: `${sender.name}@${wsA.name}`,
    lead: `${leadSeat.name}@${wsB.name}`,
    executor: `${executor.name}@${wsB.name}`,
  });

  // 设 lead
  const lead1 = await api("PATCH", `/api/projects/${PROJECT}/workstations/${wsB.id}`, token, {
    lead_seat_id: leadSeat.id,
  });
  record("设 wsB.lead_seat_id", lead1.status === 200, { status: lead1.status });

  // 跨工位派单
  const dispatchTitle = `[真验收] 真 AI 协作 ${Date.now()}`;
  const dispatchBody = "请用 markdown 列举 3 个 Phaser 3 农场游戏中可以提升用户黏性的具体功能；每条 ≤ 30 字。";
  const dispatch = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: sender.id,
    recipient_type: "thread_workstation",
    recipient_id: executor.id,
    message_type: "agent_command",
    title: dispatchTitle,
    body: dispatchBody,
    status: "queued",
  });
  const dispatchMsg = dispatch.body?.data;
  record("跨工位派单 → pending_review", dispatchMsg?.status === "pending_review", {
    msg_id: dispatchMsg?.id, recipient: dispatchMsg?.recipient_id, status: dispatchMsg?.status,
  });
  record("recipient redirect 到 lead", dispatchMsg?.recipient_id === leadSeat.id);

  // approve
  const approve = await api("POST", `/api/collaboration/messages/${dispatchMsg.id}/review/approve`, token, {});
  record("approve 通过", approve.status === 200 && approve.body?.data?.status === "queued");

  // 工位长 ack（直返 sender）
  const ackBody = `已收到，分派给 ${executor.name} 处理。`;
  const ack = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: leadSeat.id,
    recipient_type: "agent",
    recipient_id: sender.id,
    message_type: "agent_result",
    title: `[ack] ${dispatchTitle}`,
    body: ackBody,
    status: "queued",
    metadata: { receipt_kind: "ack", parent_message_id: dispatchMsg.id },
  });
  const ackMsg = ack.body?.data;
  record("ack 直返 sender + metadata 落库", ackMsg?.recipient_id === sender.id && ackMsg?.metadata?.receipt_kind === "ack", {
    metadata: ackMsg?.metadata,
  });

  // 工位长内派（如果 executor != lead）
  if (executor.id !== leadSeat.id) {
    const inner = await api("POST", `/api/collaboration/messages`, token, {
      project_id: PROJECT,
      sender_type: "agent",
      sender_id: leadSeat.id,
      recipient_type: "thread_workstation",
      recipient_id: executor.id,
      message_type: "agent_command",
      title: `[内派] ${dispatchTitle}`,
      body: dispatchBody,
      status: "queued",
      metadata: { parent_message_id: dispatchMsg.id, redispatched_from_lead: true },
    });
    record("工位长 → executor 同工位 queued", inner.body?.data?.status === "queued");
  }

  // ★★★ 真 AI 出 done body ★★★
  const aiPrompt =
`你扮演一位 Phaser 3 农场游戏设计师，正在回复来自队友的需求。
任务标题：${dispatchTitle}
任务内容：${dispatchBody}

要求：
- 用 GitHub-flavored markdown
- 必须 3 条
- 每条 ≤ 30 字
- 末尾附一行：> 由 claude -p 实时生成于 ${new Date().toLocaleString("zh-CN")}`;
  const ai = await realAiDoneBody(aiPrompt);
  record("真 claude -p 出 markdown", ai.ok && ai.body.length > 30, { len: ai.body.length, elapsed_ms: ai.elapsed });

  if (!ai.ok) process.exit(1);

  // 落 AI 输出文件
  const aiPath = join(OUT_DIR, "claude-real-output.md");
  writeFileSync(aiPath, ai.body, "utf-8");

  // done 回执直返 sender
  const done = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: executor.id,
    recipient_type: "agent",
    recipient_id: sender.id,
    message_type: "agent_result",
    title: `[done] ${dispatchTitle}`,
    body: ai.body,
    status: "queued",
    metadata: {
      receipt_kind: "done",
      parent_message_id: dispatchMsg.id,
      ai_provider: "claude",
      ai_elapsed_ms: ai.elapsed,
    },
  });
  const doneMsg = done.body?.data;
  record("done 回执（含真 AI 内容）直返 sender", doneMsg?.recipient_id === sender.id && doneMsg?.metadata?.receipt_kind === "done");

  // ====== Playwright 截图断言 ======
  log("→ 打开浏览器走 UI ...");
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  // 直接注入 farm_access_token cookie 跳过登录
  await ctx.addCookies([{
    name: "farm_access_token",
    value: token,
    domain: "127.0.0.1",
    path: "/",
    httpOnly: false,
    secure: false,
  }]);
  const page = await ctx.newPage();

  await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(OUT_DIR, "01-workbench.png"), fullPage: true });
  record("UI workbench 加载", true);

  // 点 sender 所在行 "+" 按钮把瓷砖打开（sender seat 的 row 里找 +）
  const rowContainsSender = page.locator("li", { hasText: sender.name }).first();
  const openBtn = rowContainsSender.locator("button", { hasText: "+" }).first();
  if (await openBtn.count() > 0) {
    await openBtn.click();
    await page.waitForTimeout(2500);
  } else {
    log("  未找到 + 按钮，截图当前页以 debug");
  }
  await page.screenshot({ path: join(OUT_DIR, "02-sender-tile-opened.png"), fullPage: true });

  // 在页面里搜 done 标题片段（用 dispatchTitle 的随机 ts 部分）
  const titleNeedle = dispatchTitle.split("] ")[1];
  // 消息流在瓷砖里可能需要滚动到底；先给 3 秒让消息刷新
  await page.waitForTimeout(3000);
  const titleCount = await page.getByText(titleNeedle).count();
  record("瓷砖里能看到此次派单", titleCount > 0, { needle: titleNeedle, count: titleCount });

  // 搜真 AI 内容片段
  const aiFirstLine = ai.body.split("\n").find((l) => l.trim().length > 5)?.trim().slice(0, 10) || "";
  const aiHits = aiFirstLine ? await page.getByText(aiFirstLine, { exact: false }).count() : 0;
  record("瓷砖里能看到真 AI 输出", aiHits > 0, { needle: aiFirstLine, count: aiHits });

  await page.screenshot({ path: join(OUT_DIR, "03-final-tile-with-ai.png"), fullPage: true });

  await browser.close();

  // 报告
  const passCount = events.filter((e) => e.ok).length;
  const failCount = events.filter((e) => !e.ok).length;
  const reportPath = join(OUT_DIR, "report.json");
  writeFileSync(
    reportPath,
    JSON.stringify({
      project: PROJECT,
      sender: sender.id, lead: leadSeat.id, executor: executor.id,
      dispatch_msg_id: dispatchMsg?.id,
      ack_msg_id: ackMsg?.id,
      done_msg_id: doneMsg?.id,
      ai_elapsed_ms: ai.elapsed,
      ai_output_path: aiPath,
      events,
    }, null, 2),
    "utf-8",
  );
  console.log(`\n报告：${reportPath}`);
  console.log(`小结：PASS=${passCount} FAIL=${failCount}`);
  process.exit(failCount === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
