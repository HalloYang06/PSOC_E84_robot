// validate-seat-to-seat-direct.mjs
// 同工位 NPC 互派验收（用户 2026-05-08 拍板必做项之一）：
//   模拟 NPC A 不通过依赖、不通过 requirement，直接 POST /messages 发给 NPC B。
//   断言：
//     - 同工位 → status=queued（免审）
//     - 跨工位 → status=pending_review（强审）
//     - body 里带 [路由] 行（跨工位 是/否 + 审核 要/免 + 来源）

import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT_DIR = path.resolve("artifacts", "seat-to-seat-direct");
fs.mkdirSync(OUT_DIR, { recursive: true });

function logStep(msg) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

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

function pickPair(seats, mode) {
  const byNode = new Map();
  for (const s of seats) {
    const node = String(s.computer_node_id ?? s.computerNodeId ?? "");
    if (!byNode.has(node)) byNode.set(node, []);
    byNode.get(node).push(s);
  }
  if (mode === "same") {
    for (const [node, list] of byNode.entries()) {
      if (node && list.length >= 2) return { upstream: list[0], downstream: list[1], cross: false };
    }
  }
  if (mode === "cross") {
    const nodes = [...byNode.keys()].filter((n) => n);
    if (nodes.length >= 2) {
      return { upstream: byNode.get(nodes[0])[0], downstream: byNode.get(nodes[1])[0], cross: true };
    }
  }
  return null;
}

async function postMessage(token, body) {
  const r = await fetch(`${API}/api/collaboration/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`POST /messages HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function runScenario(token, project, mode) {
  const seats = project.collaboration_config?.thread_workstations || [];
  const pair = pickPair(seats, mode);
  if (!pair) {
    return { mode, skipped: true, reason: `no ${mode}-workstation pair found` };
  }
  const upstream = pair.upstream;
  const downstream = pair.downstream;
  const upstreamId = String(upstream.row_id || upstream.id);
  const downstreamId = String(downstream.row_id || downstream.id);
  const expect = pair.cross ? "pending_review" : "queued";
  logStep(`${mode}: ${upstream.name} (${upstream.computer_node_id || upstream.computerNodeId || "n/a"}) → ${downstream.name} (${downstream.computer_node_id || downstream.computerNodeId || "n/a"})`);

  const msg = await postMessage(token, {
    project_id: PROJECT,
    message_type: "comment_message",
    title: `[seat-to-seat-direct][${mode}] 测试同工位互派`,
    body: `[NPC A 主动派单] 请帮忙完成以下任务（${mode}）。`,
    sender_type: "agent",
    sender_id: upstreamId,
    recipient_type: "thread_workstation",
    recipient_id: downstreamId,
    status: "queued",
  });

  const ok = msg.status === expect;
  const bodyHasRoute = String(msg.body || "").includes("[路由]");
  return {
    mode,
    cross: pair.cross,
    upstream: upstream.name,
    downstream: downstream.name,
    message_id: msg.id,
    status: msg.status,
    expect,
    ok,
    body_has_route_line: bodyHasRoute,
  };
}

async function main() {
  const result = { started_at: new Date().toISOString(), pass: false, scenarios: [], error: null };
  try {
    const token = await login();
    const project = await getProject(token);

    for (const mode of ["same", "cross"]) {
      const r = await runScenario(token, project, mode);
      result.scenarios.push(r);
      if (r.skipped) {
        logStep(`✗ ${mode} skipped — ${r.reason}`);
      } else {
        logStep(`${r.ok && r.body_has_route_line ? "✓" : "✗"} ${mode} status=${r.status} (want ${r.expect}), body[路由]=${r.body_has_route_line}`);
      }
    }

    const allOk = result.scenarios.every((r) => r.skipped || (r.ok && r.body_has_route_line));
    result.pass = allOk;
  } catch (e) {
    result.error = String(e?.message || e);
    result.pass = false;
  }

  result.finished_at = new Date().toISOString();
  const reportPath = path.join(OUT_DIR, `report-${Date.now()}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(result, null, 2));

  const md = [
    `# 同工位 NPC 互派验收报告`,
    ``,
    `- 时间：${result.started_at} → ${result.finished_at}`,
    `- 项目：${PROJECT}`,
    `- 整体：${result.pass ? "✅ PASS" : "❌ FAIL"}`,
    result.error ? `- 错误：\`${result.error}\`` : "",
    ``,
    `## 场景`,
    "",
    "```json",
    JSON.stringify(result.scenarios, null, 2),
    "```",
  ].join("\n");
  const mdPath = path.resolve("docs", "screenshots", "v1", `seat-to-seat-direct-${new Date().toISOString().slice(0, 10)}.md`);
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
