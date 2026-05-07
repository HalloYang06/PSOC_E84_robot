// validate-end-to-end-reply.mjs
// 第三轮验收：端到端 AI 真回断言（最重要）
//
// 用户原话（2026-05-07）：
//   "真的打通了 claude 线程和 codex 线程吗，怎么我发消息没有回复"
//   "不是只在后端验证，前端要截图验证真的看到了回消息了"
//
// 流程：
//   1. login 拿 token
//   2. 后端：选一个 seat，POST /api/messages 派一条 agent_command
//   3. 起 watcher（spawn start-thread-watcher.ps1 / 或 fallback mock）
//   4. 90s 内轮询 /api/collaboration/messages?project_id=...&agent_id=seat_id&message_type=agent_result
//   5. 前端：Playwright 打开 workbench，开瓷砖，截图 a；等回；截图 b；断言页面文本里有 agent_result 或回复片段
//   6. 后端 PASS + 前端 PASS = 真 PASS（缺一即 FAIL，不准 SKIP）
//
// 关键约束（来自 feedback_validation_must_assert_ai_reply.md）：
//   - watcher 没起 → 写 FAIL，不写 SKIP；让"watcher 没起"成为可见警告
//   - mock 模式只能验"链路通"，不能写"AI 真回 PASS"；脚本会显式标 [MOCK]

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const WEB = (process.env.WEB_BASE || "http://127.0.0.1:3100").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const POLL_TIMEOUT_MS = Number(process.env.POLL_TIMEOUT_MS || 90000);
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || 3000);
const MODE = (process.env.E2E_MODE || "auto").toLowerCase(); // auto|watcher|mock
const FORCE_SEAT_ID = process.env.SEAT_ID || "";
const OUT_DIR = path.resolve("artifacts", "end-to-end-reply");
fs.mkdirSync(OUT_DIR, { recursive: true });

const ACCESS_COOKIE = "farm_access_token";

function logStep(msg) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function loginToken(context) {
  const r = await context.request.post(`${API}/api/auth/session`, {
    data: { email: EMAIL, password: PASSWORD },
    headers: { "Content-Type": "application/json" },
  });
  if (!r.ok()) throw new Error(`login HTTP ${r.status()}: ${await r.text()}`);
  const body = await r.json();
  return body.data.access_token;
}

async function fetchProject(token) {
  const r = await fetch(`${API}/api/projects/${encodeURIComponent(PROJECT)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`get project HTTP ${r.status}: ${await r.text()}`);
  const body = await r.json();
  return body.data;
}

function pickSeat(project) {
  const cfg = project?.collaboration_config ?? {};
  const seats = cfg.thread_workstations ?? cfg.threadWorkstations ?? cfg.workstations ?? [];
  if (FORCE_SEAT_ID) {
    const found = seats.find((s) => (s.id ?? s.config_id) === FORCE_SEAT_ID);
    if (found) return found;
    throw new Error(`SEAT_ID=${FORCE_SEAT_ID} 未在 project.collaboration_config 找到`);
  }
  if (!Array.isArray(seats) || seats.length === 0) {
    throw new Error("项目没有任何 thread_workstation seat");
  }
  // 倾向选 provider=claude 或 codex 的第一个
  const preferred = seats.find((s) => /claude|codex|qwen/i.test(String(s.provider_id ?? s.providerId ?? "")));
  return preferred ?? seats[0];
}

async function dispatchCommand(token, seat) {
  const seatId = String(seat.id ?? seat.config_id);
  const dispatchId = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const body = {
    project_id: PROJECT,
    agent_id: seatId,
    recipient_type: "workstation",
    recipient_id: seatId,
    message_type: "agent_command",
    status: "queued", // /complete 要求 {queued|pending|acked|in_progress}，否则 409
    title: `[validate-end-to-end-reply] ${dispatchId}`,
    body: `这是一条端到端验收派单（${dispatchId}）。请回一句你收到了的 ack。`,
    dispatch_id: dispatchId,
    metadata: { source: "validate-end-to-end-reply.mjs" },
  };
  const r = await fetch(`${API}/api/collaboration/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`dispatch HTTP ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return { command: j.data, seatId, dispatchId };
}

async function pollAgentResult(token, seatId, dispatchId, sinceTs, deadlineAt) {
  const url = new URL(`${API}/api/collaboration/messages`);
  url.searchParams.set("project_id", PROJECT);
  url.searchParams.set("agent_id", seatId);
  url.searchParams.set("limit", "30");
  while (Date.now() < deadlineAt) {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) {
      const j = await r.json();
      const items = Array.isArray(j.data) ? j.data : (j.data?.items ?? []);
      // 1) 优先 dispatch_id 匹配（如果后端透传了 receipt 的 dispatch_id）
      const exact = items.find((m) =>
        ["agent_result", "agent_ack", "requirement_final_reply"].includes(String(m.message_type))
        && dispatchId && String(m.dispatch_id ?? "") === dispatchId
      );
      if (exact) return exact;
      // 2) 兜底：sinceTs 之后出现的、属于此 seat 的 agent_result（receipt 不复制 dispatch_id）
      const fallback = items.find((m) => {
        if (String(m.message_type) !== "agent_result") return false;
        const ts = m.created_at ? new Date(m.created_at + (m.created_at.endsWith("Z") ? "" : "Z")).getTime() : 0;
        return ts >= sinceTs - 2000; // 给 2s 时钟偏差
      });
      if (fallback) return fallback;
    }
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  return null;
}

async function postCompleteMock(token, seatId, messageId) {
  // mock 模式：直接调 /complete 写一条 agent_result
  const r = await fetch(
    `${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/thread-workstations/${encodeURIComponent(seatId)}/messages/${encodeURIComponent(messageId)}/complete`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        result_status: "completed",
        note: "[MOCK 端到端 fake reply] 协议层链路已通；此回执由 validate-end-to-end-reply.mjs 在 mock 模式下伪造，不代表 AI 真的回了。",
      }),
    },
  );
  if (!r.ok) throw new Error(`mock complete HTTP ${r.status}: ${await r.text()}`);
  return await r.json();
}

function spawnWatcher(token, seatId) {
  const isWin = process.platform === "win32";
  const ps = isWin ? "powershell.exe" : "pwsh";
  const repoRoot = path.resolve("..", ".."); // 从 apps/web 跑时
  const script = path.resolve(repoRoot, "scripts", "start-thread-watcher.ps1");
  const args = [
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", script,
    "-ProjectId", PROJECT,
    "-WorkstationId", seatId,
    "-ApiBase", API,
    "-PollSeconds", "2",
  ];
  const env = { ...process.env, PLATFORM_AUTH_TOKEN: token };
  const child = spawn(ps, args, {
    env,
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });
  const logFile = path.join(OUT_DIR, `watcher-${seatId.slice(0, 16)}.log`);
  const ws = fs.createWriteStream(logFile);
  child.stdout.on("data", (d) => ws.write(d));
  child.stderr.on("data", (d) => ws.write(d));
  child.on("error", (err) => ws.write(`[spawn error] ${err.message}\n`));
  return { child, logFile };
}

async function preflightAdapterConfig(token, seatId) {
  // watcher 起来前 adapter-config 必须 200，否则 watcher 一起就死
  const url = `${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/thread-workstations/${encodeURIComponent(seatId)}/adapter-config`;
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (r.ok) {
    const j = await r.json();
    return { ok: true, config: j.data };
  }
  const errText = await r.text();
  return { ok: false, status: r.status, errText };
}

async function shootPage(page, name) {
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1100 },
    locale: "zh-CN",
  });

  const token = await loginToken(ctx);
  for (const host of ["127.0.0.1", "localhost"]) {
    await ctx.addCookies([{
      name: ACCESS_COOKIE, value: token, domain: host, path: "/",
      httpOnly: false, secure: false, sameSite: "Lax",
    }]);
  }

  logStep("→ 取项目 + 选 seat");
  const project = await fetchProject(token);
  const seat = pickSeat(project);
  const seatId = String(seat.id ?? seat.config_id);
  const seatName = String(seat.name ?? seatId);
  logStep(`  seat = ${seatName} (${seatId.slice(0, 32)}…) provider=${seat.provider_id ?? seat.providerId ?? "?"}`);

  // 决定模式
  let actualMode = MODE;
  if (MODE === "auto") {
    actualMode = "watcher"; // 已确认本机有 claude / codex CLI
  }
  logStep(`→ 模式 = ${actualMode}${actualMode === "mock" ? " [MOCK：协议层验证，不算 AI 真回]" : ""}`);

  let watcherInfo = null;
  let watcherDisabledReason = "";
  if (actualMode === "watcher") {
    logStep("→ 预检 adapter-config（watcher 起前必须 200）");
    const pre = await preflightAdapterConfig(token, seatId);
    if (!pre.ok) {
      watcherDisabledReason = `adapter-config HTTP ${pre.status}: ${String(pre.errText).slice(0, 200)}`;
      logStep(`  ✗ 预检失败：${watcherDisabledReason}`);
      logStep(`  ⚠ watcher 不起（会立即挂掉）。脚本继续跑，让 FAIL 写进报告。`);
    } else {
      logStep(`  ✓ 预检 OK，provider=${pre.config?.provider_id ?? pre.config?.provider ?? "?"}`);
      logStep("→ spawn watcher (start-thread-watcher.ps1)");
      watcherInfo = spawnWatcher(token, seatId);
      // 等 watcher 起来（最多 6s，让它 GET adapter-config）
      await new Promise((r) => setTimeout(r, 6000));
    }
  }

  logStep("→ 开浏览器到 workbench + 截图 (before)");
  const page = await ctx.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  await page.goto(`${WEB}/projects/${PROJECT}/workbench`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(2500);
  // 打开瓷砖
  const plus = page.locator('button[title="打开瓷砖"]').first();
  if (await plus.count()) {
    await plus.click().catch(() => {});
    await page.waitForTimeout(2500);
  }
  const beforeShot = await shootPage(page, "01-before-dispatch");

  logStep("→ POST /api/collaboration/messages (agent_command)");
  const dispatchTs = Date.now();
  const { command, dispatchId } = await dispatchCommand(token, seat);
  const commandId = String(command.id ?? "");
  logStep(`  message_id=${commandId.slice(0, 12)}… dispatch_id=${dispatchId}`);

  // mock 模式立即写回
  if (actualMode === "mock") {
    logStep("→ [MOCK] 立即调 /complete 伪造 agent_result");
    await postCompleteMock(token, seatId, commandId);
  }

  logStep(`→ 后端断言：轮询 ${POLL_TIMEOUT_MS / 1000}s 找 agent_result（dispatch_id=${dispatchId} or since=${new Date(dispatchTs).toISOString()}）`);
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  const reply = await pollAgentResult(token, seatId, dispatchId, dispatchTs, deadline);

  let backendPass = false;
  let backendNote = "";
  if (reply) {
    backendPass = true;
    const replyText = String(reply.body ?? reply.content ?? "").slice(0, 120).replace(/\s+/g, " ");
    backendNote = `agent_result 出现 / type=${reply.message_type} sender=${reply.sender_type}/${String(reply.sender_id || "").slice(0, 12)} body="${replyText}"`;
  } else {
    backendNote = `${POLL_TIMEOUT_MS / 1000}s 内未见 agent_result（mode=${actualMode}）— watcher 可能没起、CLI 调用失败、或者 dispatch_id 未透传`;
  }
  logStep(`  后端断言: ${backendPass ? "PASS" : "FAIL"} — ${backendNote}`);

  logStep("→ 前端断言：刷新工作台 + 等消息流加载 + 截图 (after) + 检查文本");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  // 重新打开瓷砖
  const plus2 = page.locator('button[title="打开瓷砖"]').first();
  if (await plus2.count()) {
    await plus2.click().catch(() => {});
  }
  // 等消息流加载（messageList / 消息条目出现）
  await page.waitForTimeout(5000);
  // 在瓷砖里滚动到底，让最新消息可见
  const composer = page.locator('textarea[placeholder*="发指令"]').first();
  if (await composer.count()) {
    await composer.scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(1500);
  }
  const afterShot = await shootPage(page, "02-after-reply");

  // 前端断言：页面文本里有回复片段，或 agent_result 类型 chip
  const pageText = await page.locator("body").innerText().catch(() => "");
  const replyFragment = reply ? String(reply.body ?? reply.content ?? "").trim().slice(0, 24) : "";
  const hasReplyFragment = replyFragment ? pageText.includes(replyFragment) : false;
  const hasAgentRoleChip = /agent_result|本NPC|代发|ack|协议层链路已通/.test(pageText);
  const frontendPass = backendPass && (hasReplyFragment || hasAgentRoleChip);
  const frontendNote = backendPass
    ? (hasReplyFragment ? `页面命中回复片段 "${replyFragment}"`
       : hasAgentRoleChip ? "页面有 agent_result/ack 标签（未必是这一条）"
       : "页面文本未命中 agent_result / 回复片段（消息流可能未刷新或未渲染）")
    : "后端没回，前端无意义";
  logStep(`  前端断言: ${frontendPass ? "PASS" : "FAIL"} — ${frontendNote}`);

  // 收尾
  if (watcherInfo?.child) {
    try { watcherInfo.child.kill(); } catch {}
    logStep(`→ watcher 终止；日志在 ${watcherInfo.logFile}`);
  }

  // 报告
  const reportPath = path.join(OUT_DIR, "report.md");
  const isReal = actualMode !== "mock";
  const overallPass = backendPass && frontendPass;
  const overallTag = overallPass
    ? (isReal ? "✅ 真 PASS（AI 真回 + 前端可见）" : "🟡 协议 PASS（MOCK，不代表 AI 真回）")
    : "❌ FAIL";
  const lines = [
    `# 端到端 AI 真回 验收报告`,
    ``,
    `运行：${new Date().toISOString()}  ·  模式 = \`${actualMode}\`  ·  超时 = ${POLL_TIMEOUT_MS / 1000}s`,
    ``,
    `项目: \`${PROJECT}\`  ·  seat: \`${seatName}\` (\`${seatId}\`)  ·  provider: \`${seat.provider_id ?? seat.providerId ?? "?"}\``,
    ``,
    `## 结论：${overallTag}`,
    ``,
    `| 断言 | 结果 | 说明 |`,
    `|---|---|---|`,
    `| 后端：90s 内出现 agent_result | ${backendPass ? "✅ PASS" : "❌ FAIL"} | ${backendNote} |`,
    `| 前端：消息流页面可见 | ${frontendPass ? "✅ PASS" : "❌ FAIL"} | ${frontendNote} |`,
    ``,
    `## 截图`,
    ``,
    `- 派单前：![before](${path.basename(beforeShot)})`,
    `- 派单后：![after](${path.basename(afterShot)})`,
    ``,
    `## 派出的命令`,
    ``,
    `- message_id: \`${commandId}\``,
    `- dispatch_id: \`${dispatchId}\``,
    ``,
    actualMode === "mock"
      ? `## 注意：MOCK 模式\n\n这一轮只验"协议层链路通"。\`agent_result\` 是脚本通过 \`/messages/{id}/complete\` 接口伪造的，不代表 Claude / Codex CLI 真的回了一句话。\n要真验"AI 真回"，请：\n\n\`\`\`pwsh\nE2E_MODE=watcher node ../../scripts/validate-end-to-end-reply.mjs\n\`\`\`\n\n并确保本机 PATH 里有 \`claude\` / \`codex\` 可执行。`
      : (overallPass
          ? `## 真 PASS 含义\n\n本机 watcher 起了 → 调 CLI → 收到回执并写回平台 → 后端 \`agent_result\` 出现 → 前端工作台可见。\n这是 \`feedback_validation_must_assert_ai_reply.md\` 定义的合格门槛。`
          : `## FAIL 排查清单\n\n${watcherDisabledReason ? `**预检失败：\`${watcherDisabledReason}\`**\n\n这通常表示 seat 配的 \`computer_node_id\` 和项目 computer_nodes 表里的 id 不一致（如 \`runner_pc1\` vs \`runner-pc1\`），到工作台 NPC 头部"改身份"修。\n\n` : ""}1. \`scripts/start-thread-watcher.ps1\` 是否真起来了？看 \`${watcherInfo?.logFile ?? "(未起 watcher)"}\`。\n2. 本机 PATH 里有没有 \`claude\` / \`codex\`？\n3. seat 的 \`provider_id\` 是不是 \`claude\` / \`codex\` / \`qwen\`？\n4. ${POLL_TIMEOUT_MS / 1000}s 太短？设 \`POLL_TIMEOUT_MS=180000\` 再跑。`),
  ];
  fs.writeFileSync(reportPath, lines.join("\n"));
  logStep(`→ 报告：${reportPath}`);

  await ctx.close();
  await browser.close();

  console.log(`\n${overallTag}`);
  process.exit(overallPass ? 0 : 1);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
