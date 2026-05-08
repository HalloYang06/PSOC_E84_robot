#!/usr/bin/env node
// Step 6: 真用一遍 — 跨工位派 → 工位长接 → 转给本工位 NPC → done 回执直返发起人。
// 全程后端真表，不 mock。
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const API = process.env.API_BASE || "http://127.0.0.1:8010";
const PROJECT = process.env.PROJECT_ID || "proj_ai_collab";
const EMAIL = process.env.LOGIN_EMAIL || "lead@example.com";
const PASSWORD = process.env.LOGIN_PASSWORD || "password";

const OUT_DIR = join(process.cwd(), "artifacts", "step6-real-walk");
mkdirSync(OUT_DIR, { recursive: true });

const log = (...a) => console.log(`[${new Date().toLocaleTimeString()}]`, ...a);
const events = [];
function record(name, ok, detail) {
  events.push({ name, ok, detail });
  log(`${ok ? "✓" : "✗"} ${name}`, detail !== undefined ? JSON.stringify(detail) : "");
}

async function api(method, path, token, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let parsed;
  try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = { _raw: text }; }
  return { status: res.status, body: parsed };
}

(async () => {
  // 1. login
  const login = await api("POST", "/api/auth/session", null, { email: EMAIL, password: PASSWORD });
  const token = login.body?.data?.access_token;
  record("登录", !!token, { status: login.status });
  if (!token) process.exit(1);

  // 2. 拿工位 + NPC（seats 走 /workstations/{id}/seats 取 DB 主键；/thread-workstations 返回的 id 是 JSON alias 中文名）
  const wsResp = await api("GET", `/api/projects/${PROJECT}/workstations`, token);
  const workstations = wsResp.body?.data || [];
  const seats = [];
  for (const ws of workstations) {
    const r = await api("GET", `/api/projects/${PROJECT}/workstations/${ws.id}/seats`, token);
    const list = r.body?.data || [];
    for (const s of list) seats.push({ ...s, workstation_id: ws.id, workstation_name: ws.name });
  }

  // 选两个不同 workstation_id 的 NPC
  const byWs = new Map();
  for (const s of seats) {
    const ws = s.workstation_id;
    if (!ws) continue;
    if (!byWs.has(ws)) byWs.set(ws, []);
    byWs.get(ws).push(s);
  }
  const wsIds = [...byWs.keys()];
  if (wsIds.length < 2) {
    record("有 ≥2 工位含 NPC", false, { wsIds });
    process.exit(1);
  }
  const wsA = wsIds[0];
  const wsB = wsIds[1];
  const sender = byWs.get(wsA)[0];
  const wsBSeats = byWs.get(wsB);
  // 工位 B 内挑两个：一个当 lead，一个当真正的执行 NPC（如果只有一个就 lead 兼执行）
  const leadCandidate = wsBSeats[0];
  const executor = wsBSeats[1] || wsBSeats[0];
  record("挑两工位 ≥2 NPC", true, {
    sender: `${sender.name}@${wsA.slice(0,12)}`,
    target_lead: `${leadCandidate.name}@${wsB.slice(0,12)}`,
    executor: `${executor.name}@${wsB.slice(0,12)}`,
  });

  // 3. 设 wsB 的 lead
  const setLead = await api("PATCH", `/api/projects/${PROJECT}/workstations/${wsB}`, token, {
    lead_seat_id: leadCandidate.id,
  });
  record("设 wsB.lead_seat_id", setLead.status === 200, { status: setLead.status });

  // 4. 跨工位派单：sender → executor（非 lead），后端兜底应该 redirect 到 leadCandidate
  const dispatchTitle = `[step6] 跨工位派单 ${Date.now()}`;
  const dispatch = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: sender.id,
    recipient_type: "thread_workstation",
    recipient_id: executor.id,
    message_type: "agent_command",
    title: dispatchTitle,
    body: "Step 6 真用一遍 — 跨工位派单。请处理这条任务并发 done 回执。",
    status: "queued",
  });
  const dispatchMsg = dispatch.body?.data;
  record("跨工位派单创建", dispatch.status === 200 || dispatch.status === 201, {
    status: dispatch.status,
    msg_id: dispatchMsg?.id,
    msg_status: dispatchMsg?.status,
    recipient_id: dispatchMsg?.recipient_id,
  });
  record("recipient redirect 到 lead", dispatchMsg?.recipient_id === leadCandidate.id, {
    expected: leadCandidate.id, got: dispatchMsg?.recipient_id,
  });
  record("跨工位派单 status=pending_review", dispatchMsg?.status === "pending_review", {
    got: dispatchMsg?.status,
  });

  // 5. 审批通过
  const approve = await api("POST", `/api/collaboration/messages/${dispatchMsg.id}/review/approve`, token, {});
  const approved = approve.body?.data;
  record("approve 审批", approve.status === 200, { status: approve.status, new_status: approved?.status });

  // 6. 工位长 inbox 拉单（双队列接口：inbox=Requirement，todo=Task；这里我们派的是 Message，所以查 collaboration_messages 直接验）
  const leadInboxResp = await api(
    "GET",
    `/api/seats/${encodeURIComponent(leadCandidate.id)}/queues?limit=20`,
    token,
  );
  const leadInboxData = leadInboxResp.body?.data || {};
  const leadInbox = leadInboxData.requirement_inbox?.items || [];
  const leadTodo = leadInboxData.task_todo?.items || [];
  // 派的是 message 不是 requirement，所以双队列接口看不到这条 — 改去 messages API 验
  const leadMsgsResp = await api(
    "GET",
    `/api/collaboration/messages?project_id=${PROJECT}&recipient_type=thread_workstation&recipient_id=${encodeURIComponent(leadCandidate.id)}&limit=20`,
    token,
  );
  const leadMsgs = leadMsgsResp.body?.data || [];
  const inInbox = leadMsgs.find((m) => m.id === dispatchMsg.id);
  record("工位长 messages inbox 含此消息", !!inInbox, {
    msg_count: leadMsgs.length, found: !!inInbox,
    queue_inbox: leadInbox.length, queue_todo: leadTodo.length,
  });

  // 7. 工位长 ack — 把消息 status 改 in_progress 同时发 ack 回执
  const ack = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: leadCandidate.id,
    recipient_type: "agent",
    recipient_id: sender.id,
    message_type: "agent_result",
    title: `[ack] ${dispatchTitle}`,
    body: "工位长已收到，正在分派。",
    status: "queued",
    metadata: { receipt_kind: "ack", parent_message_id: dispatchMsg.id },
  });
  const ackMsg = ack.body?.data;
  record("ack 回执创建", !!ackMsg?.id, {
    status: ack.status, msg_id: ackMsg?.id, recipient: ackMsg?.recipient_id,
  });
  record("ack 直返 sender（不绕 lead）", ackMsg?.recipient_id === sender.id, {
    expected: sender.id, got: ackMsg?.recipient_id,
  });

  // 8. 工位长把任务派给 executor（同工位 → queued）
  let dispatchedToExecutorId = null;
  let dispatchedToExecutorStatus = null;
  if (executor.id !== leadCandidate.id) {
    const innerDispatch = await api("POST", `/api/collaboration/messages`, token, {
      project_id: PROJECT,
      sender_type: "agent",
      sender_id: leadCandidate.id,
      recipient_type: "thread_workstation",
      recipient_id: executor.id,
      message_type: "agent_command",
      title: `[内派] ${dispatchTitle}`,
      body: `工位长转交给 ${executor.name}。`,
      status: "queued",
      metadata: { parent_message_id: dispatchMsg.id, redispatched_from_lead: true },
    });
    dispatchedToExecutorId = innerDispatch.body?.data?.id;
    dispatchedToExecutorStatus = innerDispatch.body?.data?.status;
    record("工位长 → executor 同工位派单 queued", dispatchedToExecutorStatus === "queued", {
      status: innerDispatch.status, msg_status: dispatchedToExecutorStatus,
    });
  } else {
    record("executor==lead，跳过内派", true, {});
  }

  // 9. executor done 回执直返 sender
  const done = await api("POST", `/api/collaboration/messages`, token, {
    project_id: PROJECT,
    sender_type: "agent",
    sender_id: executor.id,
    recipient_type: "agent",
    recipient_id: sender.id,
    message_type: "agent_result",
    title: `[done] ${dispatchTitle}`,
    body: "## 完成\n\n- 已实现\n- github: https://example.com/pr/1\n",
    status: "queued",
    metadata: {
      receipt_kind: "done",
      parent_message_id: dispatchMsg.id,
    },
  });
  const doneMsg = done.body?.data;
  record("done 回执创建", !!doneMsg?.id, { status: done.status, msg_id: doneMsg?.id });
  record("done 直返 sender（跳过工位长）", doneMsg?.recipient_id === sender.id, {
    expected: sender.id, got: doneMsg?.recipient_id,
  });

  // 10. sender 视角：messages API 能看到 ack/done 回执
  const senderRecvResp = await api(
    "GET",
    `/api/collaboration/messages?project_id=${PROJECT}&recipient_type=agent&recipient_id=${encodeURIComponent(sender.id)}&limit=30`,
    token,
  );
  const senderRecv = senderRecvResp.body?.data || [];
  const findReceipt = (list, kind) =>
    list.find((m) => {
      const md = m.metadata || {};
      return md.receipt_kind === kind && md.parent_message_id === dispatchMsg.id;
    });
  const sawAck = findReceipt(senderRecv, "ack");
  const sawDone = findReceipt(senderRecv, "done");
  record("sender 看见 ack 回执", !!sawAck, { count: senderRecv.length });
  record("sender 看见 done 回执", !!sawDone, { count: senderRecv.length });

  // 11. 小结
  const passCount = events.filter((e) => e.ok).length;
  const failCount = events.filter((e) => !e.ok).length;
  const stamp = Date.now();
  const reportPath = join(OUT_DIR, `report-${stamp}.json`);
  writeFileSync(
    reportPath,
    JSON.stringify({
      project: PROJECT, sender: sender.id, lead: leadCandidate.id, executor: executor.id,
      dispatch_msg_id: dispatchMsg?.id, redispatched_inner_id: dispatchedToExecutorId,
      ack_msg_id: ackMsg?.id, done_msg_id: doneMsg?.id,
      events,
    }, null, 2),
    "utf-8",
  );
  console.log(`\n报告：${reportPath}`);
  console.log(`小结：PASS=${passCount} FAIL=${failCount}`);
  process.exit(failCount === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
