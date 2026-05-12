"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import styles from "./workbench.module.css";
import { NpcTile, type WorkbenchSeat } from "./_components/npc-tile";
import { apiClientUrl } from "../../../../lib/api-client-url";

type WorkbenchClientProps = {
  projectId: string;
  projectName: string;
  projectDescription?: string;
  projectGithubUrl?: string;
  projectLocalPath?: string;
  apiBaseUrl: string;
  seats: WorkbenchSeat[];
  resourceIndex?: WorkbenchResourceIndex;
  members?: WorkbenchMember[];
  messages?: WorkbenchMessage[];
  bossPlans?: WorkbenchBossPlan[];
  currentUserId: string;
  currentUserName: string;
  initialOpenSeatIds?: string[];
  initialLaunchPackSeatIds?: string[];
  surfaceNotice?: string;
  surfaceError?: string;
  pageMode?: "workbench" | "company";
  returnTo?: string;
  returnToLabel?: string;
  embedded?: boolean;
};

type WorkbenchMember = {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  isOwner: boolean;
};

type WorkbenchMessage = {
  id: string;
  title?: string | null;
  body?: string | null;
  status?: string | null;
  message_type?: string | null;
  created_at?: string | null;
  sender_type?: string | null;
  sender_id?: string | null;
  recipient_id?: string | null;
};

type WorkbenchResourceIndex = {
  computers: number;
  onlineComputers: number;
  logicalWorkstations: number;
  workshopStations: number;
  skills: number;
  projectSkills: number;
  repoReady: boolean;
  repoLocalChecked?: boolean;
  repoLocalExists?: boolean;
  repoLocalIsGit?: boolean;
  repoLocalMessage?: string;
};

type BossPlanTask = {
  id: string;
  role: string;
  targetSeatId: string;
  targetOpenId: string;
  targetName: string;
  title: string;
  body: string;
  skills: string[];
  missing: boolean;
};

type WorkbenchBossPlanItem = {
  id: string;
  role: string;
  targetSeatId: string;
  targetName: string;
  title: string;
  status: string;
  dispatchMessageId: string;
  receiptMessageId: string;
  skills: string[];
  knowledgePaths: string[];
  acceptance: string;
};

type WorkbenchBossPlan = {
  id: string;
  title: string;
  goal: string;
  status: string;
  bossSeatId: string;
  contractPath: string;
  createdAt: string;
  updatedAt: string;
  items: WorkbenchBossPlanItem[];
};

function seatApiId(seat?: WorkbenchSeat | null): string {
  return seat?.rowId || seat?.id || "";
}

function withReturnTo(href: string, returnTo: string, source = "workbench"): string {
  const [path, query = ""] = href.split("?");
  const params = new URLSearchParams(query);
  params.set("return_to", returnTo);
  params.set("from", source);
  return `${path}?${params.toString()}`;
}

function withOpenSeat(href: string, seatId: string, openIds: string[]): string {
  const [path, query = ""] = href.split("?");
  const params = new URLSearchParams(query);
  const nextIds = openIds.includes(seatId) ? openIds.filter((id) => id !== seatId) : [...openIds, seatId];
  params.delete("seat");
  if (nextIds.length) params.set("seats", nextIds.join(","));
  else params.delete("seats");
  const nextQuery = params.toString();
  return nextQuery ? `${path}?${nextQuery}` : path;
}

function isBossPlanningRole(role: string): boolean {
  const text = role.toLowerCase();
  return text.includes("boss") || text.includes("产品与分工") || text.includes("产品拆解");
}

type BossThreadNeed = {
  role: string;
  targetSeatId: string;
  targetName: string;
  provider: string;
  status: "bound" | "needs_user_thread" | "needs_npc";
  promptHint: string;
  skills: string[];
  repoPaths: string[];
};

type BossOperatingContract = {
  path: string;
  localLayout: string[];
  githubRules: string[];
  knowledgePaths: string[];
  messageRules: string[];
};

type BossPlan = {
  goal: string;
  bossName: string;
  phases: string[];
  threadNeeds: BossThreadNeed[];
  tasks: BossPlanTask[];
  missingRoles: Array<{ role: string; reason: string; skills: string[] }>;
  contract: BossOperatingContract;
};

const PROJECT_OPERATING_CONTRACT: BossOperatingContract = {
  path: "docs/ai-handoffs/project-operating-contract.md",
  localLayout: [
    "apps/api -> 后端 API、数据模型、接口测试",
    "apps/web -> 工作台、Boss 面板、用户可见协作流",
    "apps/runner -> 本地 runner / 线程桥接",
    "scripts -> watcher、验证、维护脚本",
    "docs/ai-handoffs -> 交接、NPC memory、项目契约",
    "docs/ai-requirements -> 需求、验收、设计记录",
    "artifacts -> 截图和浏览器验收报告",
  ],
  githubRules: [
    "任务和回执使用 GitHub 仓库相对路径，不写别的电脑绝对路径",
    "并行 NPC 先声明互不重叠的写入范围",
    "改代码必须返回 changed / validated / risk / next",
  ],
  knowledgePaths: [
    "项目契约（GitHub 相对路径）：docs/ai-handoffs/project-operating-contract.md",
    "工位知识库（GitHub 相对路径）：docs/workstations/<logical-workstation>.md",
    "NPC 长期记忆（GitHub 相对路径）：docs/ai-handoffs/npc-memory/<npc-slug>.md",
    "跨 NPC 交接：docs/ai-handoffs/inbox/",
    "需求与验收：docs/ai-requirements/",
  ],
  messageRules: [
    "派单正文包含 Goal / Scope / Repo paths / Knowledge paths / Required skills / Acceptance checks / Return receipt",
    "NPC 回执包含 Understood / Changed / Validated / Blocked / Next",
    "工作台显示精简消息，长日志放原文抽屉或 handoff 文档",
    "同工位 NPC 互相认识，需求先找同工位最匹配职责的 NPC；跨工位只找目标工位的工位长 NPC 转交",
  ],
};

export function WorkbenchClient({
  projectId,
  projectName,
  projectDescription = "",
  projectGithubUrl = "",
  projectLocalPath = "",
  apiBaseUrl,
  seats,
  resourceIndex,
  members = [],
  messages = [],
  bossPlans = [],
  currentUserId,
  currentUserName,
  initialOpenSeatIds = [],
  initialLaunchPackSeatIds = [],
  surfaceNotice = "",
  surfaceError = "",
  pageMode = "workbench",
  returnTo = "",
  returnToLabel = "",
  embedded = false,
}: WorkbenchClientProps) {
  const isCompany = pageMode === "company";
  const sourcePath = `/projects/${projectId}/${isCompany ? "company" : "workbench"}`;
  const sourceKey = isCompany ? "company" : "workbench";
  const [liveMessages, setLiveMessages] = useState(messages);
  const latestBossPlan = bossPlans[0] ?? null;
  const [openIds, setOpenIds] = useState<string[]>(initialOpenSeatIds);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [bossPrompt, setBossPrompt] = useState("");
  const [bossPlan, setBossPlan] = useState<BossPlan | null>(null);
  const [bossBusy, setBossBusy] = useState(false);
  const [bossNote, setBossNote] = useState<string | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [lanesOpen, setLanesOpen] = useState(false);
  const [activeToolPanel, setActiveToolPanel] = useState<"boss" | "resources" | "overview" | null>(null);
  const [autoOpenLaunchPackIds, setAutoOpenLaunchPackIds] = useState<Set<string>>(new Set(initialLaunchPackSeatIds));
  const resource = useMemo(
    () => resourceIndex ?? {
      computers: 0,
      onlineComputers: 0,
      logicalWorkstations: 0,
      workshopStations: 0,
      skills: 0,
      projectSkills: 0,
      repoReady: Boolean(projectGithubUrl || projectLocalPath),
      repoLocalChecked: false,
      repoLocalExists: false,
      repoLocalIsGit: false,
      repoLocalMessage: "",
    },
    [projectGithubUrl, projectLocalPath, resourceIndex],
  );
  const bossPlanStorageKey = `workbench:${projectId}:boss-plan:v1`;

  function rememberBossPlan(nextPlan: BossPlan | null) {
    setBossPlan(nextPlan);
    try {
      if (nextPlan) {
        window.localStorage.setItem(bossPlanStorageKey, JSON.stringify(nextPlan));
      } else {
        window.localStorage.removeItem(bossPlanStorageKey);
      }
    } catch {
      // Local persistence is a convenience; dispatch must still work without it.
    }
  }

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(bossPlanStorageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as BossPlan;
      if (parsed && typeof parsed.goal === "string" && Array.isArray(parsed.tasks)) {
        setBossPlan(parsed);
      }
    } catch {
      window.localStorage.removeItem(bossPlanStorageKey);
    }
  }, [bossPlanStorageKey]);

  useEffect(() => {
    try {
      if (bossPlan) {
        window.localStorage.setItem(bossPlanStorageKey, JSON.stringify(bossPlan));
      } else {
        window.localStorage.removeItem(bossPlanStorageKey);
      }
    } catch {
      // Local persistence is a convenience; dispatch must still work without it.
    }
  }, [bossPlan, bossPlanStorageKey]);

  const grouped = useMemo(() => {
    const groups = new Map<string, { name: string; isLogical: boolean; seats: WorkbenchSeat[] }>();
    for (const seat of seats) {
      let key = "__unbound__";
      let name = "未归属工位";
      let isLogical = false;
      if (seat.workstationId) {
        key = `ws:${seat.workstationId}`;
        name = seat.workstationName || seat.workstationId;
        isLogical = true;
      } else if (seat.computerNodeId) {
        key = `node:${seat.computerNodeId}`;
        name = seat.computerNodeName || seat.computerNodeId;
      }
      const bucket = groups.get(key) ?? { name, isLogical, seats: [] };
      bucket.seats.push(seat);
      groups.set(key, bucket);
    }
    return Array.from(groups.entries()).map(([key, value]) => ({ key, ...value }));
  }, [seats]);

  const filteredGroups = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return grouped;
    return grouped
      .map((group) => ({
        ...group,
        seats: group.seats.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            (s.workstationName || s.computerNodeName).toLowerCase().includes(q) ||
            s.responsibility.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.seats.length > 0);
  }, [grouped, filter]);
  const filteredMembers = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return members;
    return members.filter(
      (member) =>
        member.name.toLowerCase().includes(q) ||
        member.email.toLowerCase().includes(q) ||
        member.role.toLowerCase().includes(q),
    );
  }, [filter, members]);
  const filterSummary = useMemo(() => {
    const q = filter.trim();
    if (!q) return null;
    const matchedSeats = filteredGroups.reduce((sum, group) => sum + group.seats.length, 0);
    const matchedMembers = filteredMembers.length;
    const matchedGroups = filteredGroups.map((group) => group.name).join(" / ");
    const subject = isCompany ? "工位长" : "NPC";
    if (matchedSeats === 0 && matchedMembers === 0) return `没有匹配的协作者`;
    const parts = [];
    if (matchedMembers > 0) parts.push(`${matchedMembers} 位人类成员`);
    if (matchedSeats > 0) parts.push(`${matchedSeats} 个 ${subject}${matchedGroups ? `，来自 ${matchedGroups}` : ""}`);
    return `匹配到 ${parts.join(" / ")}`;
  }, [filter, filteredGroups, filteredMembers, isCompany]);

  const openSeats = useMemo(
    () => openIds.map((id) => seats.find((s) => s.id === id)).filter(Boolean) as WorkbenchSeat[],
    [openIds, seats],
  );

  const threadOverview = useMemo(() => {
    const registered = seats.filter((seat) => seat.threadId).length;
    const threadReady = seats.filter((seat) => seat.threadId && /ready|已登记|online|ok|watcher/i.test(seat.threadHealth || "")).length;
    const automationEnabled = seats.filter((seat) => seat.automationEnabled).length;
    const missing = Math.max(0, seats.length - registered);
    const byWorkspace = new Map<string, { key: string; label: string; seats: WorkbenchSeat[]; registered: number }>();
    for (const seat of seats) {
      const key = seat.workstationId || seat.computerNodeId || "__unbound__";
      const label = seat.workstationName || seat.computerNodeName || "未归属";
      const bucket = byWorkspace.get(key) ?? { key, label, seats: [], registered: 0 };
      bucket.seats.push(seat);
      if (seat.threadId) bucket.registered += 1;
      byWorkspace.set(key, bucket);
    }
    return {
      registered,
      threadReady,
      automationEnabled,
      missing,
      unboundSeats: seats.filter((seat) => !seat.threadId),
      workspaces: Array.from(byWorkspace.values()),
    };
  }, [seats]);
  const unassignedSeats = useMemo(
    () => seats.filter((seat) => !seat.workstationId),
    [seats],
  );

  const resourceLinks = useMemo(
    () => [
      {
        key: "workstations",
        label: "工位",
        value: resource.logicalWorkstations,
        href: withReturnTo(`/projects/${projectId}/2d-upgrade?panel=development-workshop`, sourcePath, sourceKey),
        warning: resource.logicalWorkstations === 0,
        hint: `${resource.workshopStations} 个岗位模板`,
      },
      {
        key: "npc",
        label: "NPC",
        value: seats.length,
        href: withReturnTo(`/projects/${projectId}/2d-upgrade?panel=npc-create`, sourcePath, sourceKey),
        warning: seats.length === 0,
        hint: `${threadOverview.registered}/${seats.length} 线程`,
      },
      {
        key: "computers",
        label: "电脑",
        value: `${resource.onlineComputers}/${resource.computers}`,
        href: withReturnTo(`/projects/${projectId}/2d-upgrade?panel=computers`, sourcePath, sourceKey),
        warning: resource.computers === 0 || resource.onlineComputers === 0,
        hint: "Runner / 扫描",
      },
      {
        key: "skills",
        label: "Skill",
        value: resource.skills,
        href: withReturnTo(`/projects/${projectId}/2d-upgrade?panel=skills`, sourcePath, sourceKey),
        warning: resource.skills === 0,
        hint: `${resource.projectSkills} 项目自定义`,
      },
      {
        key: "repo",
        label: "仓库",
        value: resource.repoReady ? "已设" : "待设",
        href: withReturnTo(`/projects/${projectId}/2d-upgrade?panel=git`, sourcePath, sourceKey),
        warning: !resource.repoReady,
        hint: "Git / 路径约定",
      },
    ],
    [projectId, resource, seats.length, sourceKey, sourcePath, threadOverview.registered],
  );

  const setupChecklist = useMemo(() => {
    return threadOverview.unboundSeats.map((seat) => {
      const lower = `${seat.name} ${seat.responsibility} ${(seat.skillLoadout || []).join(" ")}`.toLowerCase();
      const roleHint = lower.includes("backend") || lower.includes("标注") || lower.includes("导出") || lower.includes("asr")
        ? "标注、审核、数据集导出、ASR/baseline"
        : lower.includes("frontend") || lower.includes("miniapp") || lower.includes("小程序") || lower.includes("录音")
          ? "学生录音、教师后台、核心页面体验"
          : lower.includes("qa") || lower.includes("验收") || lower.includes("测试")
            ? "浏览器验收、合规风险、测试清单"
            : "按 Boss 派单承接项目任务";
      const provider = seat.providerLabel || seat.providerId || "Codex";
      return {
        seat,
        provider,
        roleHint,
        suggestedThreadName: `${projectName} / ${seat.name}`,
        skills: seat.skillLoadout && seat.skillLoadout.length ? seat.skillLoadout : (lower.includes("backend") || lower.includes("标注") || lower.includes("导出") || lower.includes("asr")
          ? ["backend-api", "dataset-export", "annotation-workflow", "contract-test"]
          : lower.includes("frontend") || lower.includes("miniapp") || lower.includes("小程序") || lower.includes("录音")
            ? ["frontend", "recording-flow", "teacher-dashboard", "playwright"]
            : lower.includes("qa") || lower.includes("验收") || lower.includes("测试")
              ? ["acceptance-test", "browser-validation", "data-compliance", "risk-check"]
              : ["requirements-ledger", "project-planning"]),
      };
    });
  }, [projectName, threadOverview.unboundSeats]);

  useEffect(() => {
    setLiveMessages(messages);
  }, [messages]);

  useEffect(() => {
    let cancelled = false;
    const refreshMessages = async () => {
      try {
        const res = await fetch(apiClientUrl(`/api/collaboration/messages?project_id=${encodeURIComponent(projectId)}&limit=100`), {
          credentials: "include",
        });
        const json = await res.json().catch(() => ({}));
        if (!cancelled && res.ok && Array.isArray(json?.data)) {
          setLiveMessages(json.data);
        }
      } catch {
        // Summary refresh is best-effort; NPC tiles still show their own fetch errors.
      }
    };
    const onUpdated = (event: Event) => {
      const detail = event instanceof CustomEvent ? (event.detail as { projectId?: string } | undefined) : undefined;
      if (detail?.projectId && detail.projectId !== projectId) return;
      refreshMessages();
    };
    window.addEventListener("workbench:collab-updated", onUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener("workbench:collab-updated", onUpdated);
    };
  }, [projectId]);

  const operationsSummary = useMemo(() => {
    const seatById = new Map<string, WorkbenchSeat>();
    for (const seat of seats) {
      for (const value of [seat.id, seat.rowId, seat.configId, seat.threadId, seat.name]) {
        if (value) seatById.set(value, seat);
      }
    }
    const statuses = liveMessages.map((message) => String(message.status || "").toLowerCase());
    const setupBlocked = liveMessages.filter((message) => {
      const status = String(message.status || "").toLowerCase();
      if (!["queued", "pending", "acked", "in_progress"].includes(status)) return false;
      const recipientId = String(message.recipient_id || "").trim();
      const seat = recipientId ? seatById.get(recipientId) : null;
      return Boolean(seat && !seat.threadId);
    }).length;
    const pendingReview = statuses.filter((status) => status === "pending_review").length;
    const active = liveMessages.filter((message) => {
      const status = String(message.status || "").toLowerCase();
      if (!["queued", "pending", "acked", "in_progress"].includes(status)) return false;
      const recipientId = String(message.recipient_id || "").trim();
      const seat = recipientId ? seatById.get(recipientId) : null;
      return !(seat && !seat.threadId);
    }).length;
    const done = statuses.filter((status) => ["completed", "done", "delivered"].includes(status)).length;
    const failed = statuses.filter((status) => ["failed", "rejected", "cancelled"].includes(status)).length;
    const latest = liveMessages
      .slice()
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0];
    return {
      pendingReview,
      setupBlocked,
      active,
      done,
      failed,
      latestTitle: latest?.title || latest?.body?.slice(0, 48) || "暂无协作消息",
      latestStatus: latest?.status || "",
    };
  }, [liveMessages, seats]);

  const pendingReviewSeatIds = useMemo(() => {
    const seatById = new Map<string, WorkbenchSeat>();
    for (const seat of seats) {
      for (const value of [seat.id, seat.rowId, seat.configId, seat.threadId, seat.name]) {
        if (value) seatById.set(value, seat);
      }
    }
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const message of liveMessages) {
      if (String(message.status || "").toLowerCase() !== "pending_review") continue;
      const seat = seatById.get(String(message.recipient_id || "").trim());
      if (!seat || seen.has(seat.id)) continue;
      ids.push(seat.id);
      seen.add(seat.id);
    }
    return ids;
  }, [liveMessages, seats]);

  function openPendingReviews() {
    openSeatGroup(pendingReviewSeatIds);
    setLanesOpen(true);
  }

  function roleScore(seat: WorkbenchSeat, keywords: string[]) {
    const haystack = [
      seat.name,
      seat.responsibility,
      seat.providerLabel,
      seat.providerId,
      seat.computerNodeName,
      ...(seat.skillLoadout || []),
      ...(seat.inheritedSkills || []),
    ].join(" ").toLowerCase();
    return keywords.reduce((sum, word) => sum + (haystack.includes(word) ? 1 : 0), 0);
  }

  const bossSeat = useMemo(() => {
    const bossKeywords = ["boss", "产品", "需求", "pm", "owner", "lead", "项目", "总控", "负责人"];
    const explicit = seats.find((seat) => roleScore(seat, bossKeywords) > 0 || seat.isLead);
    return explicit ?? null;
  }, [seats]);
  const bossThreadReady = Boolean(bossSeat?.threadId);

  function pickSeat(role: string, keywords: string[]) {
    if (seats.length === 0) return null;
    const ranked = seats
      .map((seat) => ({ seat, score: roleScore(seat, keywords) + (seat.isLead && role.includes("项目") ? 1 : 0) }))
      .sort((a, b) => b.score - a.score);
    return ranked[0]?.seat ?? seats[0];
  }

  function inferProjectGoal() {
    const typed = bossPrompt.trim();
    if (typed) return typed;
    const haystack = `${projectName} ${projectDescription} ${projectGithubUrl} ${projectLocalPath}`.toLowerCase();
    if (haystack.includes("yuespeak") || haystack.includes("english_a_agent") || haystack.includes("粤听说")) {
      return "开发 YueSpeak MVP：完成题库建设、学生录音上传、音频质检、ASR 初稿、人工标注、审核、数据集导出和 baseline 评测闭环。";
    }
    const parts = [projectName, projectDescription].map((item) => item.trim()).filter(Boolean);
    return parts.length ? `推进 ${parts.join("：")} 的可交付 MVP，并拆分线程、NPC、skill、知识库和验收口。` : "推进当前项目的可交付 MVP，并拆分线程、NPC、skill、知识库和验收口。";
  }

  function bossRoleDefs() {
    const haystack = `${projectName} ${projectDescription} ${projectGithubUrl} ${projectLocalPath}`.toLowerCase();
    if (haystack.includes("yuespeak") || haystack.includes("english_a_agent") || haystack.includes("粤听说")) {
      return [
        {
          role: "YueSpeak Boss / 产品与分工",
          keywords: ["boss", "产品", "需求", "pm", "owner", "lead", "项目", "总控", "负责人"],
          skills: ["requirements-ledger", "project-planning", "acceptance-criteria"],
          repoPaths: ["README.md", "docs/mvp", "docs/ai-handoffs", "docs/ai-requirements"],
        },
        {
          role: "YueSpeak Backend Data / 标注与导出",
          keywords: ["backend", "后端", "api", "数据", "标注", "导出", "asr", "python", "fastapi"],
          skills: ["backend-api", "dataset-export", "annotation-workflow", "contract-test"],
          repoPaths: ["docs/mvp/05_接口与数据表草案.md", "docs/mvp/04_数据集与导出规范.md", "apps/api"],
        },
        {
          role: "YueSpeak Frontend Miniapp / 学生与教师体验",
          keywords: ["frontend", "miniapp", "前端", "小程序", "ui", "ux", "页面", "录音"],
          skills: ["frontend", "recording-flow", "teacher-dashboard", "playwright"],
          repoPaths: ["docs/mvp/01_MVP产品需求文档.md", "apps/web"],
        },
        {
          role: "YueSpeak QA Acceptance / 验收与风险",
          keywords: ["qa", "验收", "测试", "playwright", "验证", "截图", "合规", "baseline"],
          skills: ["acceptance-test", "browser-validation", "data-compliance", "risk-check"],
          repoPaths: ["docs/mvp/07_研发排期与验收清单.md", "docs/mvp/08_数据合规与授权协议草案.md"],
        },
      ];
    }
    return [
      { role: "项目 Boss / 产品拆解", keywords: ["boss", "产品", "需求", "pm", "owner", "lead", "项目"], skills: ["requirements-ledger", "project-planning", "acceptance-criteria"], repoPaths: ["README.md", "docs"] },
      { role: "前端体验 / 工作流", keywords: ["frontend", "前端", "ui", "ux", "react", "页面", "交互"], skills: ["frontend", "playwright", "ui-review"], repoPaths: ["apps/web"] },
      { role: "后端接口 / 数据闭环", keywords: ["backend", "后端", "api", "数据", "python", "fastapi", "队列"], skills: ["backend-api", "database", "contract-test"], repoPaths: ["apps/api"] },
      { role: "验证验收 / 真实浏览器", keywords: ["qa", "验收", "测试", "playwright", "验证", "截图"], skills: ["acceptance-test", "browser-validation", "risk-check"], repoPaths: ["artifacts", "tests"] },
    ];
  }

  function generateBossPlan() {
    const goal = inferProjectGoal();
    const roleDefs = bossRoleDefs();
    const tasks = roleDefs.map((def, index) => {
      const seat = pickSeat(def.role, def.keywords);
      const isBossRole = def.role.includes("Boss");
      const roleMatched = seat ? roleScore(seat, def.keywords) > 0 : false;
      const missing = isBossRole ? !bossThreadReady : !seat || !roleMatched || !seat.threadId;
      const targetName = seat?.name || `建议新增：${def.role}`;
      const teammateNames = seat
        ? seats
            .filter((item) => item.id !== seat.id && ((item.workstationId || item.computerNodeId || "__unbound__") === (seat.workstationId || seat.computerNodeId || "__unbound__")))
            .map((item) => `${item.isLead ? "工位长 " : ""}${item.name}（${item.responsibility || item.providerLabel || "待补职责"}）`)
        : [];
      const otherLeads = seat
        ? seats
            .filter((item) => item.id !== seat.id && item.isLead && (item.workstationId || item.computerNodeId) !== (seat.workstationId || seat.computerNodeId))
            .map((item) => `${item.name}（${item.workstationName || item.computerNodeName || "其他工位"}）`)
        : [];
      return {
        id: `boss-task-${index + 1}`,
        role: def.role,
        targetSeatId: seatApiId(seat),
        targetOpenId: seat?.id || "",
        targetName,
        title: `${def.role}：${goal.slice(0, 34)}`,
        body: [
          `Boss NPC 拆分任务：${def.role}`,
          "",
          `用户目标：${goal}`,
          "",
          "项目运行契约：",
          `- 必读：${PROJECT_OPERATING_CONTRACT.path}`,
          "- 本地路径：各电脑自己决定 clone 到哪里，只作为当前执行目录，不能写入长期约定。",
          "- GitHub 路径：知识库、交接、文件、测试、截图说明都必须用 repo-relative path。",
          projectGithubUrl ? `- GitHub 仓库：${projectGithubUrl}` : "- GitHub 仓库：未绑定",
          projectLocalPath ? `- 本机参考路径：${projectLocalPath}` : "- 本机参考路径：未绑定",
          `- 建议先读：${def.repoPaths.join("；")}`,
          `- 知识库：${PROJECT_OPERATING_CONTRACT.knowledgePaths.join("；")}`,
          `- 推荐 skill：${def.skills.join("、")}`,
          "",
          "NPC 路由协议（必须遵守）：",
          `- 本 NPC 所在工位：${seat?.workstationName || seat?.computerNodeName || "未归属工位"}`,
          `- 同工位通讯录：${teammateNames.length ? teammateNames.join("；") : "暂无同工位伙伴；先向 Boss NPC 回执缺口"}`,
          `- 跨工位入口：${otherLeads.length ? otherLeads.join("；") : "暂无其他工位长；跨工位需求先回 Boss NPC"}`,
          "- 有需求时先判断职责关键词：同工位能处理就直接找对应 NPC；不确定就问同工位工位长；跨工位不要直连普通 NPC，只找目标工位工位长转交。",
          "- 工位长收到跨工位需求后，负责判断本工位哪个 NPC 最合适，并在完成后给上游 NPC / Boss NPC 精简回执。",
          "",
          "请按这个派单格式执行：",
          "Goal:",
          "Scope:",
          "Repo paths:",
          "Knowledge paths:",
          "Required skills:",
          "Acceptance checks:",
          "Return receipt:",
          "",
          "请只在你的职责范围内推进，并给 Boss NPC 返回精简回执：",
          "Understood:",
          "Changed:",
          "Validated:",
          "Blocked:",
          "Next:",
        ].join("\n"),
        skills: def.skills,
        missing,
      };
    });
    const threadNeeds = tasks.map((task) => {
      const seat = task.targetSeatId ? seats.find((item) => seatApiId(item) === task.targetSeatId || item.id === task.targetSeatId) : null;
      const provider = seat?.providerLabel || seat?.providerId || "Codex";
      const status: BossThreadNeed["status"] = !seat
        ? "needs_npc"
        : seat.threadId
          ? "bound"
          : "needs_user_thread";
      return {
        role: task.role,
        targetSeatId: task.targetSeatId,
        targetName: task.targetName,
        provider,
        status,
        skills: task.skills,
        repoPaths: roleDefs.find((def) => def.role === task.role)?.repoPaths ?? [],
        promptHint: status === "bound"
          ? `${task.targetName} 已绑定 ${provider} 线程`
          : status === "needs_npc"
            ? `先创建 ${task.role} NPC，再让用户开一个 ${provider} 线程绑定`
            : `用户开一个 ${provider} 线程，绑定给 ${task.targetName}，再点 NPC 上岗包生成提示词/skill/知识库`,
      };
    });
    rememberBossPlan({
      goal,
      bossName: bossThreadReady && bossSeat ? bossSeat.name : "未绑定 Boss NPC",
      phases: ["澄清目标和验收口", "创建或补齐 NPC/skill", "按工位派单执行", "收集回执并二次分派", "浏览器/测试验收后给用户最终回复"],
      threadNeeds,
      tasks,
      contract: PROJECT_OPERATING_CONTRACT,
      missingRoles: tasks
        .filter((task) => task.missing)
        .map((task) => ({
          role: task.role,
          reason: task.role.includes("Boss")
            ? "Boss NPC 也必须绑定用户已创建的执行线程；绑定前只能规划需要几个线程，不能代表项目派工。"
            : task.targetSeatId
              ? "这个 NPC 已存在，但还没有绑定用户创建的执行线程；先开线程、绑定并生成上岗包后再派发。"
            : "当前没有明显匹配职责/skill 的 NPC，建议先创建或补装 skill。",
          skills: task.skills,
        })),
    });
    setBossNote(null);
  }

  async function dispatchBossPlan() {
    if (!bossPlan) {
      setBossNote("先生成 Boss NPC 分工方案。");
      return;
    }
    if (!bossSeat || !bossSeat.threadId) {
      setBossNote("先给 Boss NPC 绑定用户已创建的执行线程；Boss 线程未登记前不能代表项目派发。");
      return;
    }
    const dispatchable = bossPlan.tasks.filter((task) => task.targetSeatId && !task.missing && !isBossPlanningRole(task.role));
    if (dispatchable.length === 0) {
      setBossNote("当前没有可直接派发的执行 NPC。先按缺口提示绑定 Backend / Frontend / QA 等执行线程。");
      return;
    }
    setBossBusy(true);
    setBossNote(null);
    try {
      const results = await Promise.all(
        dispatchable.map(async (task) => {
          const targetSeat = seats.find((item) => seatApiId(item) === task.targetSeatId || item.id === task.targetOpenId);
          const bossGroup = bossSeat ? seatGroupKey(bossSeat) : "";
          const targetGroup = targetSeat ? seatGroupKey(targetSeat) : "";
          const needsHumanReview = Boolean(bossGroup && targetGroup && bossGroup !== targetGroup);
          const routeSeat = needsHumanReview
            ? seats.find((item) => item.isLead && seatGroupKey(item) === targetGroup)
            : targetSeat;
          if (!routeSeat) {
            throw new Error(
              needsHumanReview
                ? `${task.targetName}: 目标工位还没有工位长，先在主页面给该工位设置 lead NPC。`
                : `${task.targetName}: 未找到目标 NPC，请先回主页面绑定线程/NPC。`,
            );
          }
          const routeSeatId = seatApiId(routeSeat);
          const routedBody = needsHumanReview
            ? [
                task.body,
                "",
                "----",
                "平台路由说明:",
                `- Boss 原始目标 NPC: ${task.targetName}`,
                `- 跨工位入口 NPC: ${routeSeat.name}`,
                "- 请目标工位长先审核任务、选择本工位最匹配 NPC，再把任务转交给最终执行者。",
              ].join("\n")
            : task.body;
          const res = await fetch(apiClientUrl("/api/collaboration/messages"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({
              project_id: projectId,
              message_type: "requirement_dispatch",
              title: needsHumanReview ? `${task.title}（跨工位，经 ${routeSeat.name}）` : task.title,
              body: routedBody,
              sender_type: "agent",
              sender_id: seatApiId(bossSeat),
              recipient_type: "thread_workstation",
              recipient_id: routeSeatId,
              status: needsHumanReview ? "pending_review" : "queued",
              metadata: {
                source: "boss_npc_project_generator",
                boss_name: bossPlan.bossName,
                goal: bossPlan.goal,
                role: task.role,
                recommended_skills: task.skills,
                route_review_reason: needsHumanReview ? "cross_workstation_boss_dispatch" : "same_workstation_boss_dispatch",
                upstream_seat_id: seatApiId(bossSeat),
                downstream_seat_id: task.targetSeatId,
                routed_recipient_seat_id: routeSeatId,
                routed_recipient_name: routeSeat.name,
                intended_target_seat_id: task.targetSeatId,
                intended_target_name: task.targetName,
              },
            }),
          });
          const json = await res.json().catch(() => ({}));
          if (!res.ok) {
            const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
            throw new Error(`${task.targetName}: ${typeof msg === "string" ? msg : JSON.stringify(msg)}`);
          }
          return task;
        }),
      );
      openSeatGroup(results.map((task) => {
        const targetSeat = seats.find((item) => seatApiId(item) === task.targetSeatId || item.id === task.targetOpenId);
        const bossGroup = bossSeat ? seatGroupKey(bossSeat) : "";
        const targetGroup = targetSeat ? seatGroupKey(targetSeat) : "";
        const needsHumanReview = Boolean(bossGroup && targetGroup && bossGroup !== targetGroup);
        const routeSeat = needsHumanReview ? seats.find((item) => item.isLead && seatGroupKey(item) === targetGroup) : targetSeat;
        return routeSeat?.id || task.targetOpenId || task.targetSeatId;
      }));
      setBossNote(`已派发 ${results.length} 个子任务。真实执行仍由各 NPC 绑定的线程完成，工作台只显示精简回执。`);
    } catch (e) {
      setBossNote(`派发失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setBossBusy(false);
    }
  }

  async function recordBossPlanToBossThread() {
    if (!bossPlan) {
      setBossNote("先生成 Boss NPC 分工方案。");
      return;
    }
    if (!bossSeat || !bossSeat.threadId) {
      setBossNote("先给 Boss NPC 绑定用户已创建的执行线程；Boss 线程未登记前不能写入立项自检。");
      return;
    }
    const readyTasks = bossPlan.tasks.filter((task) => task.targetSeatId && !task.missing);
    const blockedTasks = bossPlan.tasks.filter((task) => task.missing);
    const body = [
      `Boss NPC 立项自检：${bossPlan.goal}`,
      "",
      "平台定位：",
      "- 真实处理过程留在绑定的 Codex / Claude Code 线程。",
      "- 工作台只显示分工摘要、最小回执、审核结果、阻塞和最终结果。",
      "",
      "当前可执行：",
      ...(readyTasks.length
        ? readyTasks.map((task) => `- ${task.role} -> ${task.targetName}；skill：${task.skills.join("、")}`)
        : ["- 暂无已绑定执行 NPC。"]),
      "",
      "线程 / Skill 缺口：",
      ...(blockedTasks.length
        ? blockedTasks.map((task) => `- ${task.role}：先绑定用户创建的执行线程，再派发；建议 skill：${task.skills.join("、")}`)
        : ["- 暂无缺口。"]),
      "",
      "GitHub 相对知识库路径：",
      ...bossPlan.contract.knowledgePaths.map((item) => `- ${item}`),
      "",
      "Boss 下一步：",
      "- 先把 YueSpeak 第一阶段拆成数据闭环验收口。",
      "- 只给已绑定线程的 NPC 派发可执行任务。",
      "- 未绑定 NPC 只生成上岗包、skill、知识库和线程提示。",
      "- 收到回执后再判断是否需要跨工位转交。",
      "",
      "回执格式：",
      "Understood:",
      "Changed:",
      "Validated:",
      "Blocked:",
      "Next:",
    ].join("\n");
    setBossBusy(true);
    setBossNote(null);
    try {
      const res = await fetch(apiClientUrl("/api/collaboration/messages"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          project_id: projectId,
          message_type: "requirement_dispatch",
          title: `Boss 立项自检：${bossPlan.goal.slice(0, 32)}`,
          body,
          sender_type: "human",
          sender_id: currentUserId,
          recipient_type: "thread_workstation",
          recipient_id: seatApiId(bossSeat),
          status: "queued",
          metadata: {
            source: "boss_npc_project_generator",
            goal: bossPlan.goal,
            blocked_roles: blockedTasks.map((task) => task.role),
            ready_roles: readyTasks.map((task) => task.role),
          },
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      openSeatGroup([bossSeat.id]);
      window.dispatchEvent(new CustomEvent("workbench:collab-updated", { detail: { projectId, action: "boss-kickoff" } }));
      setBossNote("已写入 Boss 对话框。下一步在 Boss 窗口接单、回执，再按已绑定线程继续派发。");
    } catch (e) {
      setBossNote(`写入 Boss 失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setBossBusy(false);
    }
  }

  function seatGroupKey(s: WorkbenchSeat): string {
    return s.workstationId || s.computerNodeId || "";
  }

  const teammatesBySeat = useMemo(() => {
    const map = new Map<string, WorkbenchSeat[]>();
    for (const seat of seats) {
      const myKey = seatGroupKey(seat);
      const peers = seats.filter(
        (other) => other.id !== seat.id && (myKey ? seatGroupKey(other) === myKey : !seatGroupKey(other)),
      );
      map.set(seat.id, peers);
    }
    return map;
  }, [seats]);

  const crossLeadsBySeat = useMemo(() => {
    const map = new Map<string, WorkbenchSeat[]>();
    const seenLeadIds = new Set<string>();
    const allLeads = seats.filter((s) => {
      if (!s.isLead || !seatGroupKey(s)) return false;
      if (seenLeadIds.has(s.id)) return false;
      seenLeadIds.add(s.id);
      return true;
    });
    for (const seat of seats) {
      const myKey = seatGroupKey(seat);
      const others = allLeads.filter(
        (lead) => seatGroupKey(lead) !== myKey && lead.id !== seat.id,
      );
      map.set(seat.id, others);
    }
    return map;
  }, [seats]);

  function toggleOpen(id: string) {
    setOpenIds((curr) => (curr.includes(id) ? curr : [...curr, id]));
  }

  function closeOpen(id: string) {
    setOpenIds((curr) => curr.filter((x) => x !== id));
  }

  function toggleSelected(id: string) {
    setSelectedIds((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openAllSelected() {
    if (selectedIds.size === 0) return;
    setOpenIds((curr) => {
      const next = [...curr];
      for (const id of selectedIds) if (!next.includes(id)) next.push(id);
      return next;
    });
  }

  function openSeatGroup(ids: string[]) {
    if (ids.length === 0) return;
    setOpenIds((curr) => {
      const next = [...curr];
      for (const id of ids) if (!next.includes(id)) next.push(id);
      return next;
    });
  }

  function openLaunchPackForSeat(id: string) {
    setAutoOpenLaunchPackIds((curr) => {
      const next = new Set(curr);
      next.add(id);
      return next;
    });
    openSeatGroup([id]);
  }

  function closeAllOpen() {
    setOpenIds([]);
  }

  const bossDispatchableCount = bossPlan
    ? bossPlan.tasks.filter((task) => task.targetSeatId && !task.missing && !isBossPlanningRole(task.role)).length
    : 0;

  return (
    <main className={styles.shell} data-embed={embedded ? "drawer" : undefined}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <Link href={`/projects/${projectId}/cockpit`} className={styles.backLink} title="返回项目驾驶舱">
            ← 驾驶舱
          </Link>
          {returnTo ? (
            <Link href={returnTo} className={styles.backLink} title="回到刚才进入工作台的位置">
              {returnToLabel || "← 返回来源"}
            </Link>
          ) : null}
          <div className={styles.title}>
            <strong>{projectName}</strong>
            <small>
              {isCompany
                ? "🏢 公司层 · 工位长会议室（每个工位的 lead 瓷砖；跨工位转交、群组决策都从这里发起）"
                : "协同工作台 · 人 / NPC / 多电脑线程协作现场"}
            </small>
          </div>
        </div>
        <div className={styles.topbarRight}>
          <span className={styles.kpi}>成员 {members.length}</span>
          <span className={styles.kpi}>
            {isCompany ? `共 ${seats.length} 位工位长` : `共 ${seats.length} 个 NPC`}
          </span>
          <span className={styles.kpi}>已打开 {openIds.length}</span>
          <span className={styles.kpi}>已勾选 {selectedIds.size}</span>
          {isCompany ? (
            <Link href={`/projects/${projectId}/workbench`} className={styles.backLink} title="返回 NPC 工作台（看所有 NPC）">
              工作台 →
            </Link>
          ) : (
            <Link href={`/projects/${projectId}/company`} className={styles.backLink} title="进入公司层：只看每个工位的工位长">
              🏢 公司层 →
            </Link>
          )}
          <Link
            href={withReturnTo(`/projects/${projectId}/datasets`, sourcePath, sourceKey)}
            className={styles.backLink}
            title="打开训练数据采集、标注、质检和导出工作台"
          >
            数据工场 →
          </Link>
          <Link
            href={withReturnTo(`/projects/${projectId}/ai-lab`, sourcePath, sourceKey)}
            className={styles.backLink}
            title="打开 AI 调试、仿真和审批边界工作台"
          >
            AI 实验室 →
          </Link>
          <Link
            href={withReturnTo(`/projects/${projectId}/robotics`, sourcePath, sourceKey)}
            className={styles.backLink}
            title="打开 App、Linux、ROS、硬件和 VLA 机器人现场"
          >
            机器人现场 →
          </Link>
          <Link
            href={withReturnTo(`/projects/${projectId}/observability`, sourcePath, sourceKey)}
            className={styles.backLink}
            title="打开派单、回执、待审、Runner 和风险观测台"
          >
            观测台 →
          </Link>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <input
              type="search"
              className={styles.search}
              placeholder="搜索成员 / NPC / 电脑 / 职责"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button
              type="button"
              className={styles.batchBtn}
              onClick={openAllSelected}
              disabled={selectedIds.size === 0}
              title="把勾选的 NPC 全部加到右侧瓷砖"
            >
              开启已勾选 ({selectedIds.size})
            </button>
            {filterSummary ? <p className={styles.searchHint}>{filterSummary}</p> : null}
          </div>

          {filteredGroups.length === 0 && filteredMembers.length === 0 ? (
            <p className={styles.empty}>没有匹配的协作者。</p>
          ) : (
            <ul className={styles.groupList}>
              {filteredMembers.length > 0 ? (
                <li className={styles.group}>
                  <div className={styles.groupHeader}>
                    <span>👥 人类成员</span>
                    <small>{filteredMembers.length} 位成员</small>
                  </div>
                  <ul className={styles.npcList}>
                    {filteredMembers.map((member) => {
                      const active = member.status === "active";
                      return (
                        <li key={member.id} className={styles.memberRow} data-current={member.id === currentUserId ? "1" : undefined}>
                          <div className={styles.memberAvatar} title={member.email || member.name}>
                            {member.name.slice(0, 1).toUpperCase()}
                          </div>
                          <div className={styles.npcMain}>
                            <strong className={styles.npcName}>
                              {member.name}
                              {member.id === currentUserId ? "（我）" : ""}
                            </strong>
                            <small className={styles.npcMeta}>
                              <span className={active ? styles.dotOnline : styles.dot} />
                              {member.isOwner ? "owner" : member.role || "member"}
                              {member.email ? ` · ${member.email}` : ""}
                            </small>
                          </div>
                          <span className={styles.memberStatus} data-active={active ? "1" : "0"}>
                            {active ? "active" : member.status || "unknown"}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ) : null}
              {filteredGroups.map((group) => (
                <li key={group.key} className={styles.group}>
                  <div className={styles.groupHeader}>
                    <span>{group.isLogical ? "🏷 " : "🖥 "}{group.name}</span>
                    <small>{group.seats.length} 个 NPC{group.isLogical ? " · 逻辑工位" : ""}</small>
                  </div>
                  <ul className={styles.npcList}>
                    {group.seats.map((seat) => {
                      const isOpen = openIds.includes(seat.id);
                      const isSelected = selectedIds.has(seat.id);
                      return (
                        <li key={seat.id} className={`${styles.npcRow} ${isOpen ? styles.npcRowOpen : ""}`}>
                          <label className={styles.checkbox} title="勾选后批量开启">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelected(seat.id)}
                            />
                          </label>
                          <div className={styles.npcMain}>
                            <strong className={styles.npcName}>{seat.name}</strong>
                            <small className={styles.npcMeta}>
                              <span className={styles.dot} title="占用状态：S5 后接入" />
                              {seat.providerLabel || "未绑定 provider"}
                              {seat.automationEnabled ? " · 自动化已开" : ""}
                            </small>
                          </div>
                          <Link
                            href={withOpenSeat(sourcePath, seat.id, openIds)}
                            className={styles.openBtn}
                            data-workbench-open-tile={seat.id}
                            onClick={(event) => {
                              event.preventDefault();
                              isOpen ? closeOpen(seat.id) : toggleOpen(seat.id);
                            }}
                            title={isOpen ? "关闭瓷砖" : "打开瓷砖"}
                          >
                            {isOpen ? "✕" : "+"}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className={styles.main} data-mode={openSeats.length > 0 ? "chat" : "setup"} data-tool-open={activeToolPanel || undefined}>
          {openSeats.length > 0 ? (
            <aside className={styles.toolRail} aria-label="工作台工具栏">
              <button
                type="button"
                className={styles.toolRailBtn}
                data-active={activeToolPanel === "boss" ? "1" : undefined}
                onClick={() => setActiveToolPanel((value) => (value === "boss" ? null : "boss"))}
              >
                Boss
              </button>
              <button
                type="button"
                className={styles.toolRailBtn}
                data-active={activeToolPanel === "resources" ? "1" : undefined}
                onClick={() => setActiveToolPanel((value) => (value === "resources" ? null : "resources"))}
              >
                资源
              </button>
              <button
                type="button"
                className={styles.toolRailBtn}
                data-active={activeToolPanel === "overview" ? "1" : undefined}
                onClick={() => setActiveToolPanel((value) => (value === "overview" ? null : "overview"))}
              >
                总览
                {operationsSummary.pendingReview > 0 ? <span>{operationsSummary.pendingReview}</span> : null}
              </button>
            </aside>
          ) : null}
          {activeToolPanel ? (
            <button type="button" className={styles.toolScrim} aria-label="关闭工具浮窗" onClick={() => setActiveToolPanel(null)} />
          ) : null}
          <section className={styles.bossPanel} data-testid="boss-npc-project-generator" data-active={openSeats.length === 0 || activeToolPanel === "boss" ? "1" : undefined}>
            <div className={styles.bossHead}>
              <div>
                <strong>Boss NPC 项目生成器</strong>
                <small>
                  {bossThreadReady && bossSeat
                    ? `${bossSeat.name} 的线程已绑定，负责把一句话目标拆成工位/NPC/skill/验收口`
                    : bossSeat
                      ? `${bossSeat.name} 可能是 Boss，但还没有绑定真实线程；先登记 Codex thread id`
                      : "先创建一个 Boss NPC，并像其它 NPC 一样绑定 Codex 线程"}
                </small>
              </div>
              <span>{bossThreadReady ? (bossPlan ? `${bossPlan.tasks.length} 个子任务` : "Boss 线程就绪") : "Boss 线程未绑定"}</span>
            </div>
            <div className={styles.bossBody}>
              {surfaceNotice || surfaceError ? (
                <p className={styles.surfaceNotice} data-error={surfaceError ? "1" : undefined}>
                  {surfaceError || surfaceNotice}
                </p>
              ) : null}
              <div className={styles.bossCommandRow}>
                <textarea
                  className={styles.bossInput}
                  value={bossPrompt}
                  onChange={(e) => setBossPrompt(e.target.value)}
                  placeholder="可选：补充本轮目标。留空时 Boss 会根据项目资料、仓库和现有 NPC 自动生成线程与分工建议。"
                  rows={2}
                />
                <div className={styles.bossActions}>
                  <button type="button" className={styles.bossPrimaryBtn} onClick={generateBossPlan} disabled={bossBusy}>
                    {bossPrompt.trim() ? "生成方案" : "自动生成方案"}
                  </button>
                  <button type="button" className={styles.threadOverviewBtn} onClick={recordBossPlanToBossThread} disabled={bossBusy || !bossPlan || !bossThreadReady}>
                    {bossBusy ? "写入中..." : "发给 Boss"}
                  </button>
                  <button type="button" className={styles.threadOverviewBtn} onClick={dispatchBossPlan} disabled={bossBusy || !bossPlan || !bossThreadReady || bossDispatchableCount === 0}>
                    {bossBusy ? "派发中..." : bossPlan ? `派发 (${bossDispatchableCount})` : "派发"}
                  </button>
                </div>
              </div>
              {bossNote ? <small className={styles.bossNote}>{bossNote}</small> : null}
              {latestBossPlan ? (
                <section className={styles.bossServerPlan} aria-label="服务端 Boss 分工闭环">
                  <div>
                    <strong>最近 Boss Plan</strong>
                    <small>{latestBossPlan.status || "unknown"} · {latestBossPlan.items.length} 个子任务</small>
                  </div>
                  <p>{latestBossPlan.title || latestBossPlan.goal}</p>
                  {latestBossPlan.contractPath ? <code>{latestBossPlan.contractPath}</code> : null}
                  <div className={styles.bossServerItems}>
                    {latestBossPlan.items.slice(0, 4).map((item) => (
                      <span key={item.id} data-status={item.status}>
                        {item.role || item.targetName}: {item.status || "planned"}
                      </span>
                    ))}
                  </div>
                </section>
              ) : null}
              {bossPlan ? (
                <div className={styles.bossPlan}>
                  <div className={styles.bossContract}>
                    <div>
                      <strong>项目运行契约</strong>
                      <small>{bossPlan.contract.path}</small>
                    </div>
                    <div className={styles.bossContractGrid}>
                      <section>
                        <span>本地结构</span>
                        {bossPlan.contract.localLayout.slice(0, 4).map((item) => <p key={item}>{item}</p>)}
                      </section>
                      <section>
                        <span>GitHub 约定</span>
                        {bossPlan.contract.githubRules.map((item) => <p key={item}>{item}</p>)}
                      </section>
                      <section>
                        <span>知识库</span>
                        {bossPlan.contract.knowledgePaths.map((item) => <p key={item}>{item}</p>)}
                      </section>
                      <section>
                        <span>消息格式</span>
                        {bossPlan.contract.messageRules.slice(0, 2).map((item) => <p key={item}>{item}</p>)}
                      </section>
                    </div>
                  </div>
                  <div className={styles.bossPhases}>
                    {bossPlan.phases.map((phase, index) => (
                      <span key={phase}>{index + 1}. {phase}</span>
                    ))}
                  </div>
                  <div className={styles.bossThreadNeeds}>
                    <div>
                      <strong>线程建议</strong>
                      <small>用户先开真实线程；平台再绑定到 NPC 并生成上岗包。</small>
                    </div>
                    {bossPlan.threadNeeds.map((item) => (
                      <p key={`${item.role}-${item.targetName}`} data-status={item.status}>
                        <span>{item.status === "bound" ? "已绑" : item.status === "needs_npc" ? "缺 NPC" : "待开线程"}</span>
                        {item.role}：{item.promptHint}
                        {item.status !== "bound" ? ` 推荐 skill：${item.skills.join("、")}；先读：${item.repoPaths.join("、")}` : ""}
                      </p>
                    ))}
                  </div>
                  <div className={styles.bossTaskGrid}>
                    {bossPlan.tasks.map((task) => (
                      <article key={task.id} className={styles.bossTask} data-missing={task.missing ? "1" : undefined}>
                        <div>
                          <strong>{task.role}</strong>
                          <small>{task.missing ? "建议新建/补 skill" : `派给 ${task.targetName}`}</small>
                        </div>
                        <p>{task.title}</p>
                        <div>
                          {task.skills.map((skill) => (
                            <span key={skill}>{skill}</span>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                  {bossPlan.missingRoles.length > 0 ? (
                    <div className={styles.bossMissing}>
                      <strong>创建 NPC / skill 缺口</strong>
                      {bossPlan.missingRoles.map((item) => (
                        <p key={item.role}>{item.role}：{item.reason} 推荐 skill：{item.skills.join("、")}</p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className={styles.bossPrepBar}>
                <div>
                  <strong>协作准备</strong>
                  <small>Boss 先判断要几个执行线程；主页面负责创建 NPC、电脑、工位和 Skill，工作台只索引并执行协作。</small>
                </div>
                <Link href={withReturnTo(`/projects/${projectId}/2d-upgrade?panel=npc-create`, sourcePath, sourceKey)} className={styles.threadOverviewLink}>
                  去主页面创建 NPC
                </Link>
              </div>
            </div>
          </section>
          <nav className={styles.resourceIndex} aria-label="项目资源索引" data-active={openSeats.length === 0 || activeToolPanel === "resources" ? "1" : undefined}>
            <div className={styles.resourceIndexHead}>
              <strong>项目资源索引</strong>
              <small>创建和治理在主页面；这个工作台只索引并使用这些资源。</small>
            </div>
            <div className={styles.resourceIndexLinks}>
              {resourceLinks.map((item) => (
                <Link key={item.key} href={item.href} className={styles.resourceIndexLink} data-warning={item.warning ? "1" : undefined}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <small>{item.hint}</small>
                </Link>
              ))}
            </div>
          </nav>
          {unassignedSeats.length > 0 ? (
            <section className={styles.workstationWarning}>
              <div>
                <strong>先补逻辑工位，协作才会正确</strong>
                <p>
                  当前 {unassignedSeats.length} 个 NPC 还没有归属逻辑工位。同工位互相认识、工位知识库、跨工位走工位长，都依赖这里的归属关系。
                </p>
              </div>
              <Link href={withReturnTo(`/projects/${projectId}/2d-upgrade?panel=development-workshop`, sourcePath, sourceKey)} className={styles.threadOverviewLink}>
                去主页面配置工位
              </Link>
            </section>
          ) : null}
          {resource.repoLocalChecked && !resource.repoLocalIsGit ? (
            <section className={styles.workstationWarning} data-tone="danger">
              <div>
                <strong>当前项目的本地仓库路径还不能用于 Git 协作</strong>
                <p>
                  {resource.repoLocalMessage || "本地工程目录不是 Git 仓库。"}
                  {" "}
                  知识库可以继续用 GitHub 相对路径，但代码开发、回退索引和 Runner 执行前，需要先在主页面 Git 治理里修正仓库来源。
                </p>
              </div>
              <Link href={withReturnTo(`/projects/${projectId}/2d-upgrade?panel=git`, sourcePath, sourceKey)} className={styles.threadOverviewLink}>
                去主页面修 Git
              </Link>
            </section>
          ) : null}
          {openSeats.length === 0 ? null : (
            <div className={styles.tileGrid} data-tile-count={openSeats.length}>
              {openSeats.map((seat) => (
                <NpcTile
                  key={seat.id}
                  projectId={projectId}
                  apiBaseUrl={apiBaseUrl}
                  seat={seat}
                  teammates={teammatesBySeat.get(seat.id) ?? []}
                  crossLeads={crossLeadsBySeat.get(seat.id) ?? []}
                  currentUserId={currentUserId}
                  currentUserName={currentUserName}
                  launchPackAutoOpen={autoOpenLaunchPackIds.has(seat.id)}
                  onOpenTeammate={toggleOpen}
                  sourcePath={sourcePath}
                  onClose={() => closeOpen(seat.id)}
                />
              ))}
            </div>
          )}
          <details className={styles.threadOverview} open={openSeats.length === 0 || activeToolPanel === "overview" ? true : undefined} data-active={openSeats.length === 0 || activeToolPanel === "overview" ? "1" : undefined}>
            <summary className={styles.threadOverviewSummary}>
              <span>协作总览</span>
              <small>
                待审 {operationsSummary.pendingReview}
                {" / "}
                进行中 {operationsSummary.active}
                {" / "}
                完成 {operationsSummary.done}
                {" / "}
                异常 {operationsSummary.failed}
              </small>
            </summary>
            <div className={styles.productStatus}>
              <strong>协同工作台 MVP</strong>
              <span data-hot={operationsSummary.pendingReview > 0 ? "1" : undefined}>待审 {operationsSummary.pendingReview}</span>
              <span data-hot={operationsSummary.setupBlocked > 0 ? "1" : undefined}>待绑定 {operationsSummary.setupBlocked}</span>
              <span>进行中 {operationsSummary.active}</span>
              <span>完成 {operationsSummary.done}</span>
              <span data-hot={operationsSummary.failed > 0 ? "1" : undefined}>异常 {operationsSummary.failed}</span>
              <small>{operationsSummary.latestTitle}{operationsSummary.latestStatus ? ` · ${operationsSummary.latestStatus}` : ""}</small>
            </div>
            {operationsSummary.pendingReview > 0 ? (
              <div className={styles.pendingReviewJump}>
                <div>
                  <strong>有 {operationsSummary.pendingReview} 条协作待审</strong>
                  <small>审核卡会显示在对应 NPC 对话框内，正文可展开，放行后才进入目标线程队列。</small>
                </div>
                <button type="button" className={styles.threadOverviewBtn} onClick={openPendingReviews}>
                  打开待审对话框
                </button>
              </div>
            ) : null}
            {setupChecklist.length > 0 ? (
              <div className={styles.setupChecklist}>
                <div className={styles.setupChecklistHead}>
                  <div>
                    <strong>待绑定线程</strong>
                    <small>用户先开线程；平台生成上岗包和知识库约定。</small>
                  </div>
                  <button type="button" className={styles.threadOverviewBtn} onClick={() => setSetupOpen((value) => !value)}>
                    {setupOpen ? "收起" : `展开 ${setupChecklist.length} 个`}
                  </button>
                </div>
                {setupOpen ? (
                  <div className={styles.setupChecklistGrid}>
                    {setupChecklist.map((item) => (
                      <article key={item.seat.id} className={styles.setupItem}>
                        <div>
                          <strong>{item.seat.name}</strong>
                          <span>{item.provider}</span>
                        </div>
                        <p>{item.roleHint}</p>
                        <code>{item.suggestedThreadName}</code>
                        <small className={styles.setupItemSkills}>{item.skills.slice(0, 4).join(" / ")}</small>
                        <button
                          type="button"
                          className={styles.threadOverviewBtn}
                          onClick={() => openLaunchPackForSeat(item.seat.id)}
                        >
                          打开上岗包
                        </button>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className={styles.setupSummary}>
                    {setupChecklist.map((item) => item.seat.name).join(" / ")}
                  </p>
                )}
              </div>
            ) : null}
            <div className={styles.threadOverviewHead}>
              <strong>{isCompany ? "工位长线程总览" : "多线程协作总览"}</strong>
              <span>线程 {threadOverview.registered}/{seats.length}</span>
              <span>线程就绪 {threadOverview.threadReady}</span>
              <span data-warning={threadOverview.automationEnabled > 0 ? "1" : undefined}>NPC 自动化 {threadOverview.automationEnabled}</span>
              <span data-warning={threadOverview.missing > 0 ? "1" : undefined}>未登记 {threadOverview.missing}</span>
              <button type="button" className={styles.threadOverviewBtn} onClick={() => openSeatGroup(seats.map((seat) => seat.id))} disabled={seats.length === 0}>
                打开全部
              </button>
              <button type="button" className={styles.threadOverviewBtn} onClick={() => openSeatGroup(seats.filter((seat) => !seat.threadId).map((seat) => seat.id))} disabled={threadOverview.missing === 0}>
                打开未登记
              </button>
              <button type="button" className={styles.threadOverviewBtn} onClick={closeAllOpen} disabled={openIds.length === 0}>
                收起全部
              </button>
              <button type="button" className={styles.threadOverviewBtn} onClick={() => setLanesOpen((value) => !value)}>
                {lanesOpen || openSeats.length === 0 ? "收起工位" : "展开工位"}
              </button>
            </div>
            {lanesOpen || openSeats.length === 0 ? (
              <div className={styles.threadLaneList}>
                {threadOverview.workspaces.map((workspace) => (
                  <div key={workspace.key} className={styles.threadLane}>
                    <div className={styles.threadLaneTitle}>
                      <strong>{workspace.label}</strong>
                      <button
                        type="button"
                        onClick={() => openSeatGroup(workspace.seats.map((seat) => seat.id))}
                        title={`打开 ${workspace.label} 下全部 NPC`}
                      >
                        {workspace.registered}/{workspace.seats.length} 线程
                      </button>
                    </div>
                    <div className={styles.threadChips}>
                      {workspace.seats.map((seat) => (
                        <button
                          key={seat.id}
                          type="button"
                          className={styles.threadChipBtn}
                          data-open={openIds.includes(seat.id) ? "1" : undefined}
                          data-missing={seat.threadId ? undefined : "1"}
                          onClick={() => toggleOpen(seat.id)}
                          title={`${seat.name} · ${seat.threadKind || seat.providerLabel || seat.providerId || "thread"} · ${seat.threadId || "未登记真实线程"}`}
                        >
                          <span>{seat.name}</span>
                          <small>{seat.threadId ? (seat.threadKind || seat.providerLabel || seat.providerId || "thread") : "未登记"}</small>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </details>
          {openSeats.length === 0 ? (
            <div className={styles.placeholder}>
              <strong>
                {isCompany
                  ? seats.length === 0
                    ? "还没有任何工位长"
                    : "点击左栏工位长行的 + 号，打开 ta 的会议室瓷砖"
                  : "选择左栏的人或 NPC，查看这个项目里的协作现场"}
              </strong>
              <p>
                {isCompany
                  ? "公司层只显示每个工位指定的工位长（👑）。在工位卡的「工位长」下拉里选定后会出现在这里。跨工位的消息默认会被路由到对应工位长。"
                  : "人类成员负责决策、审核和接手；NPC 绑定 Codex 线程负责执行。同工位协作默认顺滑，跨工位协作走工位长和审核。"}
              </p>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
