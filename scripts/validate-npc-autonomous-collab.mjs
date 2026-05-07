// validate-npc-autonomous-collab.mjs
// 自主合作专项验收（用户拍板必做项）
//
// 用户原话（2026-05-08）：
//   "然后 NPC 之间的合作"
//   "还有工位之间的自主交流，记住这两项啊，别觉得难就不干，然后这两项都要加人工审批，也可以免审"
//
// 流程（按 项目→工位→NPC→线程 结构）：
//   1. 选项目里两个 seat（NPC1, NPC2）；如果同 computer_node_id → 同工位（免审），否则跨工位（要审）
//   2. 创建父需求 A（target_seat_id=NPC1, trigger_kind=manual）
//   3. 创建子需求 B（target_seat_id=NPC2, trigger_kind=on_requirement_done, dependency_requirement_id=A.id）
//   4. 完成 A（POST /api/requirements/{A}/final-reply, status=done）
//   5. 断言 30s 内出现一条 sender_type=agent / sender_id=NPC1.id / recipient_id=NPC2.id 的 requirement_dispatch
//   6. 断言下游 requirement.status: 同工位免审 → queued；跨工位要审 → blocked
//   7. 报告写到 docs/screenshots/v1/npc-autonomous-collab-report-{date}.md
//
// 不依赖 watcher 起来（这是协议层验收，watcher 是另一条链）

import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const POLL_TIMEOUT_MS = Number(process.env.POLL_TIMEOUT_MS || 30000);
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || 1500);
const OUT_DIR = path.resolve("artifacts", "npc-autonomous-collab");
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

function pickPair(project) {
  const cfg = project?.collaboration_config ?? {};
  const seats = cfg.thread_workstations ?? cfg.threadWorkstations ?? cfg.workstations ?? [];
  if (!Array.isArray(seats) || seats.length < 2) {
    throw new Error("项目至少需要 2 个 NPC seat 才能验自主合作");
  }
  // 环境变量 FORCE_MODE=cross|same 可强制走某种模式
  const forceMode = (process.env.FORCE_MODE || "").toLowerCase();
  const byNode = new Map();
  for (const s of seats) {
    const node = String(s.computer_node_id ?? s.computerNodeId ?? "");
    if (!byNode.has(node)) byNode.set(node, []);
    byNode.get(node).push(s);
  }
  const sameWorkstationPair = (() => {
    for (const [node, list] of byNode.entries()) {
      if (list.length >= 2 && node) return { upstream: list[0], downstream: list[1], cross: false };
    }
    return null;
  })();
  const crossWorkstationPair = (() => {
    const nodes = [...byNode.keys()].filter((n) => n);
    if (nodes.length >= 2) {
      return { upstream: byNode.get(nodes[0])[0], downstream: byNode.get(nodes[1])[0], cross: true };
    }
    return null;
  })();
  if (forceMode === "cross" && crossWorkstationPair) return crossWorkstationPair;
  if (forceMode === "same" && sameWorkstationPair) return sameWorkstationPair;
  return sameWorkstationPair || crossWorkstationPair || { upstream: seats[0], downstream: seats[1], cross: false };
}

async function createRequirement(token, payload) {
  const r = await fetch(`${API}/api/requirements`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`create requirement HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function dispatchRequirement(token, reqId, targetId) {
  const r = await fetch(`${API}/api/requirements/${encodeURIComponent(reqId)}/dispatch`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      actor_type: "human",
      target_type: "workstation",
      target_id: targetId,
      status: "queued",
      title: "[validate-npc-autonomous-collab] dispatch upstream",
      body: "请处理这个父需求（端到端测试）。",
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`dispatch HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function finalReply(token, reqId, senderSeatId) {
  const r = await fetch(`${API}/api/requirements/${encodeURIComponent(reqId)}/final-reply`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      sender_type: "agent",
      sender_id: senderSeatId,
      recipient_type: "project",
      message: "已完成父需求（端到端验收最终回执）。",
      status: "done",
      title: "父需求 done",
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`final-reply HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function getRequirement(token, reqId) {
  const r = await fetch(`${API}/api/requirements?project_id=${encodeURIComponent(PROJECT)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`list requirements HTTP ${r.status}: ${JSON.stringify(j)}`);
  return (j.data || []).find((x) => x.id === reqId) || null;
}

async function approveMessage(token, messageId) {
  const r = await fetch(`${API}/api/collaboration/messages/${encodeURIComponent(messageId)}/review/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`approve HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function rejectMessage(token, messageId) {
  const r = await fetch(`${API}/api/collaboration/messages/${encodeURIComponent(messageId)}/review/reject`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`reject HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
}

async function pollAutoMessage(token, downstreamReqId, deadlineAt) {
  const url = `${API}/api/collaboration/messages?project_id=${encodeURIComponent(PROJECT)}&requirement_id=${encodeURIComponent(downstreamReqId)}&message_type=requirement_dispatch`;
  while (Date.now() < deadlineAt) {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) {
      const j = await r.json().catch(() => ({}));
      const list = j.data || [];
      const hit = list.find((m) => m.sender_type === "agent" && (m.title || "").includes("自主合作"));
      if (hit) return hit;
    }
    await new Promise((res) => setTimeout(res, POLL_INTERVAL_MS));
  }
  return null;
}

async function main() {
  const result = {
    started_at: new Date().toISOString(),
    project: PROJECT,
    pass: false,
    steps: [],
    error: null,
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
    step("fetch project", true, project.id);
    const { upstream, downstream, cross } = pickPair(project);
    const upstreamSeatId = String(upstream.id ?? upstream.config_id);
    const downstreamSeatId = String(downstream.id ?? downstream.config_id);
    step("pick pair", true, {
      upstream: upstream.name,
      upstream_node: upstream.computer_node_id ?? upstream.computerNodeId,
      downstream: downstream.name,
      downstream_node: downstream.computer_node_id ?? downstream.computerNodeId,
      cross_workstation: cross,
    });

    // 创建父需求 A
    const reqA = await createRequirement(token, {
      project_id: PROJECT,
      title: `[autonomous-collab] 父需求 ${Date.now()}`,
      requirement_type: "thread_request",
      priority: "high",
      context_summary: "由 validate-npc-autonomous-collab.mjs 创建的父需求。",
      expected_output: "完成后请触发下游子需求。",
      to_agent: upstreamSeatId,
      target_seat_id: upstreamSeatId,
      trigger_kind: "manual",
    });
    step("create parent requirement A", true, { id: reqA.id });

    // 派发父需求（让它有 to_agent）
    await dispatchRequirement(token, reqA.id, upstreamSeatId);
    step("dispatch parent A → NPC1", true);

    // 创建子需求 B（依赖 A，trigger=on_requirement_done）
    const reqB = await createRequirement(token, {
      project_id: PROJECT,
      title: `[autonomous-collab] 子需求 ${Date.now()}`,
      requirement_type: "thread_request",
      priority: "high",
      context_summary: "由父需求 A 完成自动触发。",
      expected_output: "请基于 A 的产出继续推进。",
      to_agent: downstreamSeatId,
      target_seat_id: downstreamSeatId,
      trigger_kind: "on_requirement_done",
      dependency_requirement_id: reqA.id,
    });
    step("create child requirement B (trigger=on_requirement_done)", true, {
      id: reqB.id,
      dependency: reqA.id,
    });

    // 完成 A → 应该自动触发派给 NPC2
    const beforeAt = new Date().toISOString();
    await finalReply(token, reqA.id, upstreamSeatId);
    step("complete parent A (final-reply done)", true);

    // 轮询：B 上是否出现 sender_type=agent / sender_id=NPC1 的 requirement_dispatch
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    const auto = await pollAutoMessage(token, reqB.id, deadline);
    if (!auto) {
      step("poll autonomous dispatch on B", false, "30s 内未出现 sender_type=agent 的自主派单");
      throw new Error("autonomous dispatch not observed");
    }
    step("poll autonomous dispatch on B", true, {
      message_id: auto.id,
      sender_type: auto.sender_type,
      sender_id: auto.sender_id,
      recipient_id: auto.recipient_id,
      status: auto.status,
      title: auto.title,
    });

    // 断言：sender 是上游 NPC（可能是 row id 也可能是 config_id，二者其一即可）
    const upstreamConfigId = String(upstream.config_id || upstream.id);
    const upstreamRowId = String(upstream.row_id || upstream.id);
    const acceptedUpstreamIds = new Set([upstreamSeatId, upstreamConfigId, upstreamRowId]);
    if (!acceptedUpstreamIds.has(String(auto.sender_id || ""))) {
      step("assert sender_id=NPC1 (row_id or config_id)", false, { got: auto.sender_id, expect_one_of: [...acceptedUpstreamIds] });
      throw new Error(`sender_id mismatch: got ${auto.sender_id}, expect one of ${[...acceptedUpstreamIds].join("|")}`);
    }
    step("assert sender_id=NPC1 (row_id or config_id)", true, { got: auto.sender_id });

    if (!String(auto.recipient_id || "").includes(downstreamSeatId) && auto.recipient_id !== downstreamSeatId) {
      // recipient 可能是 workstation config_id；进一步对照 downstream config_id
      const downstreamConfigId = String(downstream.config_id || downstream.id);
      if (auto.recipient_id !== downstreamConfigId) {
        step("assert recipient is downstream workstation", false, {
          got: auto.recipient_id,
          expect_one_of: [downstreamSeatId, downstreamConfigId],
        });
        throw new Error("recipient not pointing to downstream workstation");
      }
    }
    step("assert recipient is downstream workstation", true);

    // 断言下游 status：同工位免审 → queued / 跨工位要审 → blocked or pending_review
    const reqBAfter = await getRequirement(token, reqB.id);
    if (cross) {
      const expectStatuses = ["pending_review", "blocked"];
      if (!expectStatuses.includes(reqBAfter.status)) {
        step("assert cross-workstation requires review", false, {
          got: reqBAfter.status,
          expect_one_of: expectStatuses,
        });
        throw new Error("cross-workstation should require review");
      }
      step("assert cross-workstation requires review", true, { status: reqBAfter.status });

      // 跨工位场景：测 approve → 应该 queued
      const approved = await approveMessage(token, auto.id);
      if (approved.status !== "queued") {
        step("assert approve flips message to queued", false, { got: approved.status });
        throw new Error("approve did not flip message to queued");
      }
      step("assert approve flips message to queued", true);
      const reqBAfterApprove = await getRequirement(token, reqB.id);
      if (reqBAfterApprove.status !== "queued") {
        step("assert approve flips requirement to queued", false, { got: reqBAfterApprove.status });
        throw new Error("approve did not flip requirement to queued");
      }
      step("assert approve flips requirement to queued", true);
    } else {
      if (reqBAfter.status !== "queued") {
        step("assert same-workstation skip review", false, {
          got: reqBAfter.status,
          expect: "queued",
        });
        throw new Error("same-workstation should skip review");
      }
      step("assert same-workstation skip review", true, { status: reqBAfter.status });
    }

    result.pass = true;
    result.summary = {
      cross_workstation: cross,
      auto_dispatch_message_id: auto.id,
      downstream_status: reqBAfter.status,
    };
  } catch (e) {
    result.error = String(e?.message || e);
    result.pass = false;
  }

  result.finished_at = new Date().toISOString();
  const reportPath = path.join(OUT_DIR, `report-${Date.now()}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(result, null, 2));

  // 写人类可读 markdown
  const mdLines = [
    `# NPC 自主合作验收报告`,
    ``,
    `- 时间：${result.started_at} → ${result.finished_at}`,
    `- 项目：${PROJECT}`,
    `- 整体：${result.pass ? "✅ PASS" : "❌ FAIL"}`,
    result.error ? `- 错误：\`${result.error}\`` : "",
    ``,
    `## 步骤`,
    ``,
    ...result.steps.map((s) => `- ${s.ok ? "✓" : "✗"} **${s.name}**${s.detail ? " — `" + (typeof s.detail === "string" ? s.detail : JSON.stringify(s.detail)) + "`" : ""}`),
    ``,
  ];
  if (result.summary) {
    mdLines.push(`## 摘要`, ``, "```json", JSON.stringify(result.summary, null, 2), "```");
  }
  const mdPath = path.resolve("docs", "screenshots", "v1", `npc-autonomous-collab-report-${new Date().toISOString().slice(0, 10)}.md`);
  fs.mkdirSync(path.dirname(mdPath), { recursive: true });
  fs.writeFileSync(mdPath, mdLines.join("\n"));

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
