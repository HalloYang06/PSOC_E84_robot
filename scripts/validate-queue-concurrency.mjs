// validate-queue-concurrency.mjs
// 任务队列并发原子化验收：5 个并发 ack 同一条 workstation 命令，断言只有 1 个 200，其余 409。
//
// 背景（2026-05-08）：
//   原 ack_workstation_command / complete_workstation_command 直接 message.status=...，
//   没有 WHERE 守护，两个 watcher 同时拉到同一条会双跑（多花 token）。
//   修复后用 db.query(...).filter(status.in_([...])).update(...) + rowcount=0 → 409。
//
// 用法：
//   API_BASE=http://127.0.0.1:8010 PROJECT_ID=proj_ai_collab \
//   LOGIN_EMAIL=lead@example.com LOGIN_PASSWORD=password \
//   node scripts/validate-queue-concurrency.mjs

import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const FANOUT = Number(process.env.FANOUT || 5);
const OUT_DIR = path.resolve("artifacts", "queue-concurrency");
fs.mkdirSync(OUT_DIR, { recursive: true });

function logStep(msg) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
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

async function fetchProject(token) {
  const r = await fetch(`${API}/api/projects/${encodeURIComponent(PROJECT)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`get project HTTP ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return j.data;
}

function pickFirstWorkstation(project) {
  const cfg = project?.collaboration_config ?? {};
  const seats = cfg.thread_workstations ?? cfg.threadWorkstations ?? cfg.workstations ?? [];
  if (!Array.isArray(seats) || seats.length < 1) {
    throw new Error("项目至少需要 1 个 NPC seat 才能验队列并发");
  }
  return seats[0];
}

async function createWorkstationCommand(token, workstationConfigId) {
  const url = `${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/thread-workstations/${encodeURIComponent(workstationConfigId)}/messages`;
  const r = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      message_type: "agent_command",
      title: "[validate-queue-concurrency] 测试命令",
      body: "并发 ack 测试用，请忽略。",
      recipient_type: "workstation",
      recipient_id: workstationConfigId,
      status: "queued",
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`create workstation message HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data.message;
}

async function ackOnce(token, workstationConfigId, messageId, idx) {
  const url = `${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/thread-workstations/${encodeURIComponent(workstationConfigId)}/messages/${encodeURIComponent(messageId)}/ack`;
  const t0 = Date.now();
  const r = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ note: `concurrent ack #${idx}` }),
  });
  const text = await r.text();
  let body = text;
  try {
    body = JSON.parse(text);
  } catch {}
  return { idx, status: r.status, took_ms: Date.now() - t0, body };
}

async function main() {
  const result = {
    started_at: new Date().toISOString(),
    project: PROJECT,
    fanout: FANOUT,
    pass: false,
    steps: [],
    error: null,
    responses: [],
  };
  function step(name, ok, detail) {
    const entry = { name, ok, detail };
    result.steps.push(entry);
    logStep(`${ok ? "✓" : "✗"} ${name}${detail ? " — " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : ""}`);
  }

  try {
    const token = await loginToken();
    step("login", true);
    const project = await fetchProject(token);
    const seat = pickFirstWorkstation(project);
    const workstationConfigId = String(seat.config_id || seat.id);
    step("pick first workstation", true, { name: seat.name, config_id: workstationConfigId });

    const message = await createWorkstationCommand(token, workstationConfigId);
    step("create agent_command (status=queued)", true, { id: message.id, status: message.status });

    // 并发 N 路 ack
    const responses = await Promise.all(
      Array.from({ length: FANOUT }).map((_, i) => ackOnce(token, workstationConfigId, message.id, i)),
    );
    result.responses = responses.map((r) => ({ idx: r.idx, status: r.status, took_ms: r.took_ms }));
    const ok200 = responses.filter((r) => r.status === 200);
    const conflict409 = responses.filter((r) => r.status === 409);
    step("concurrent ack fanout", true, { fanout: FANOUT, ok200: ok200.length, conflict409: conflict409.length });

    if (ok200.length !== 1) {
      step("assert exactly 1 success", false, { got: ok200.length, want: 1 });
      throw new Error(`exactly 1 success expected, got ${ok200.length}`);
    }
    step("assert exactly 1 success", true);

    if (conflict409.length !== FANOUT - 1) {
      step("assert remaining are 409", false, { got: conflict409.length, want: FANOUT - 1 });
      throw new Error(`expected ${FANOUT - 1} × 409, got ${conflict409.length}`);
    }
    step("assert remaining are 409", true);

    // 校验 409 错误码
    const wrongCode = conflict409.find((r) => {
      const code = r.body && typeof r.body === "object" ? (r.body.error?.code || r.body.code) : null;
      return code !== "MESSAGE_ALREADY_CLAIMED";
    });
    if (wrongCode) {
      step("assert 409 error code = MESSAGE_ALREADY_CLAIMED", false, { sample: wrongCode.body });
      throw new Error("409 missing MESSAGE_ALREADY_CLAIMED");
    }
    step("assert 409 error code = MESSAGE_ALREADY_CLAIMED", true);

    result.pass = true;
  } catch (e) {
    result.error = String(e?.message || e);
    result.pass = false;
  }

  result.finished_at = new Date().toISOString();
  const reportPath = path.join(OUT_DIR, `report-${Date.now()}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(result, null, 2));

  const md = [
    `# 任务队列并发原子化验收报告`,
    ``,
    `- 时间：${result.started_at} → ${result.finished_at}`,
    `- 项目：${PROJECT}`,
    `- 并发数：${FANOUT}`,
    `- 整体：${result.pass ? "✅ PASS" : "❌ FAIL"}`,
    result.error ? `- 错误：\`${result.error}\`` : "",
    ``,
    `## 步骤`,
    ``,
    ...result.steps.map((s) => `- ${s.ok ? "✓" : "✗"} **${s.name}**${s.detail ? " — \`" + (typeof s.detail === "string" ? s.detail : JSON.stringify(s.detail)) + "\`" : ""}`),
    ``,
    `## 响应分布`,
    ``,
    "```json",
    JSON.stringify(result.responses, null, 2),
    "```",
  ].join("\n");
  const mdPath = path.resolve("docs", "screenshots", "v1", `queue-concurrency-${new Date().toISOString().slice(0, 10)}.md`);
  fs.mkdirSync(path.dirname(mdPath), { recursive: true });
  fs.writeFileSync(mdPath, md);

  console.log(`\n报告：`);
  console.log(`  json: ${reportPath}`);
  console.log(`  md:   ${mdPath}`);
  console.log(`整体：${result.pass ? "✅ PASS" : "❌ FAIL"}`);
  process.exit(result.pass ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
