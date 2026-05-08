// validate-cross-workstation-lead-redirect.mjs
// Step 5 验收：跨工位 NPC→NPC 时，后端兜底把 recipient redirect 到目标工位的 lead_seat_id。
//
// 步骤：
//   1. 找到两个分别含 ≥2 NPC 的工位 nodeA、nodeB
//   2. 在 nodeB 上挑一个 NPC 设为工位长（PATCH workstation-profiles）
//   3. NPC A (来自 nodeA) → POST /messages 给 nodeB 的"非工位长" NPC X
//   4. 断言：返回的 message.recipient_id == nodeB 的工位长 id（不是 X.id）
//   5. body 含 "经工位长 ... 转交（原始目标 NPC: X ..."
//   6. 清理：unset lead_seat_id

import fs from "node:fs";
import path from "node:path";

const API = (process.env.API_BASE || "http://127.0.0.1:8010").replace(/\/$/, "");
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";
const OUT_DIR = path.resolve("artifacts", "cross-workstation-lead");
fs.mkdirSync(OUT_DIR, { recursive: true });

function log(m) { console.log(`[${new Date().toISOString().slice(11, 19)}] ${m}`); }

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

async function patchProfile(token, nodeId, body) {
  const r = await fetch(`${API}/api/collaboration/projects/${encodeURIComponent(PROJECT)}/workstation-profiles/${encodeURIComponent(nodeId)}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`PATCH profile HTTP ${r.status}: ${JSON.stringify(j)}`);
  return j.data;
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

async function main() {
  const result = { started_at: new Date().toISOString(), pass: false, steps: [] };
  let restoreLeadId = null;
  let nodeBId = null;
  try {
    const token = await login();
    log("✓ login");
    const project = await getProject(token);
    const seats = project.collaboration_config?.thread_workstations || [];

    const byNode = new Map();
    for (const s of seats) {
      const nid = String(s.computer_node_id || "");
      if (!nid) continue;
      if (!byNode.has(nid)) byNode.set(nid, []);
      byNode.get(nid).push(s);
    }
    // target 工位需要 ≥2 NPC（lead + 非 lead 目标）；upstream 只需在另一个工位有 ≥1
    const targetCandidates = [...byNode.entries()].filter(([, list]) => list.length >= 2);
    if (targetCandidates.length === 0) {
      throw new Error(`需要至少一个含 ≥2 NPC 的工位作为 target`);
    }
    const [nodeB, listB] = targetCandidates[0];
    const otherEntry = [...byNode.entries()].find(([nid, list]) => nid !== nodeB && list.length >= 1);
    if (!otherEntry) {
      throw new Error(`需要在 ${nodeB} 之外再有一个工位含 ≥1 NPC（用作 upstream）`);
    }
    const [nodeA, listA] = otherEntry;
    nodeBId = nodeB;
    const upstream = listA[0];
    const lead = listB[0];
    const target = listB[1];
    log(`✓ A 工位 ${nodeA} → A 上游=${upstream.name}`);
    log(`✓ B 工位 ${nodeB} → 工位长=${lead.name}, 目标=${target.name}`);

    const cfg = project.collaboration_config || {};
    const profiles = cfg.workstation_profiles || {};
    const prevProfile = profiles[nodeB] || {};
    restoreLeadId = prevProfile.lead_seat_id || prevProfile.leadSeatId || null;

    const leadId = String(lead.row_id || lead.id);
    await patchProfile(token, nodeB, { lead_seat_id: leadId });
    log(`✓ B 工位长 lead_seat_id 设为 ${leadId} (${lead.name})`);

    const upstreamId = String(upstream.row_id || upstream.id);
    const targetId = String(target.row_id || target.id);
    log(`POST /messages: ${upstream.name} (${nodeA}) → ${target.name} (${nodeB}, 非工位长)`);
    const msg = await postMessage(token, {
      project_id: PROJECT,
      message_type: "comment_message",
      title: `[step5] 跨工位 redirect 测试`,
      body: `请协助处理以下任务（跨工位 → 由后端兜底转交工位长）。`,
      sender_type: "agent",
      sender_id: upstreamId,
      recipient_type: "thread_workstation",
      recipient_id: targetId,
      status: "queued",
    });
    log(`✓ 消息创建：id=${msg.id} status=${msg.status} recipient_id=${msg.recipient_id}`);

    const recipientNotTarget = String(msg.recipient_id || "") !== targetId;
    const recipientIsLead = String(msg.recipient_id || "") === leadId;
    const bodyHasViaLead = String(msg.body || "").includes("经工位长") && String(msg.body || "").includes("原始目标");

    result.steps.push({ name: "recipient_id 已被 redirect（不再等于原目标）", ok: recipientNotTarget, detail: { recipient_id: msg.recipient_id, target_id: targetId } });
    result.steps.push({ name: "recipient_id 等于工位长 id", ok: recipientIsLead, detail: { recipient_id: msg.recipient_id, lead_id: leadId } });
    result.steps.push({ name: "body 含「经工位长 ... 转交（原始目标 NPC ...）」", ok: bodyHasViaLead, detail: { body_tail: String(msg.body || "").slice(-220) } });

    result.pass = result.steps.every((s) => s.ok);
  } catch (e) {
    result.error = String(e?.message || e);
    result.pass = false;
  } finally {
    if (nodeBId) {
      try {
        const token = await login();
        await patchProfile(token, nodeBId, { lead_seat_id: restoreLeadId || null });
        log(`✓ 已恢复 B 工位 lead_seat_id=${restoreLeadId || "(空)"}`);
      } catch (e) {
        log(`⚠ 清理失败：${e?.message || e}`);
      }
    }
  }
  result.finished_at = new Date().toISOString();

  for (const s of result.steps) log(`${s.ok ? "✓" : "✗"} ${s.name} — ${JSON.stringify(s.detail)}`);
  log(`整体: ${result.pass ? "✅ PASS" : "❌ FAIL"}`);

  const reportPath = path.join(OUT_DIR, `report-${Date.now()}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(result, null, 2));
  console.log(`\n报告：${reportPath}`);
  process.exit(result.pass ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
