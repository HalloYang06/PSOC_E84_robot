export type LoginMode = "人类" | "智能体" | "观察者";
export type CollaboratorKind = "人类" | "智能体";
export type CollaboratorStatus = "在线" | "工作中" | "待确认" | "待接手" | "离线";
export type MemberStatus = "在线" | "工作中" | "待确认" | "离线";
export type InvitationStatus = "待发送" | "待接受" | "已接受" | "已拒绝";

export type LoginDraft = {
  id: string;
  name: string;
  role: string;
  project: string;
  computer: string;
  thread: string;
  mode: LoginMode;
  note: string;
  remember: boolean;
  updatedAt: string;
};

export type Collaborator = {
  id: string;
  name: string;
  kind: CollaboratorKind;
  role: string;
  computer: string;
  status: CollaboratorStatus;
  currentTask: string;
  skills: string[];
  note: string;
  enabled: boolean;
  updatedAt: string;
};

export type Member = {
  id: string;
  name: string;
  email: string;
  kind: CollaboratorKind;
  role: string;
  project: string;
  thread: string;
  computer: string;
  status: MemberStatus;
  note: string;
  enabled: boolean;
  updatedAt: string;
};

export type Invitation = {
  id: string;
  email: string;
  name: string;
  project: string;
  role: string;
  thread: string;
  note: string;
  status: InvitationStatus;
  createdAt: string;
};

export type AuthSummary = {
  users: number;
  pending_invitations: number;
  accepted_invitations: number;
  project_members: number;
};

export const LOGIN_STORAGE_KEY = "ai-collab-login-draft";
export const RECENT_LOGIN_STORAGE_KEY = "ai-collab-login-recent";
export const COLLABORATOR_STORAGE_KEY = "ai-collab-collaborators";
export const MEMBER_STORAGE_KEY = "ai-collab-member-roster";
export const INVITATION_STORAGE_KEY = "ai-collab-member-invites";

export const DEFAULT_PROJECT = "AI协作平台第一版";

export const LOGIN_PRESETS: Array<{
  label: string;
  draft: Partial<LoginDraft>;
}> = [
  {
    label: "总工程师",
    draft: {
      name: "总工程师",
      role: "项目主理",
      mode: "人类",
      note: "负责范围、验收和真机确认。",
    },
  },
  {
    label: "前端协作者",
    draft: {
      name: "前端协作者",
      role: "界面与交互",
      mode: "智能体",
      note: "负责页面、表单和协作入口。",
    },
  },
  {
    label: "后端协作者",
    draft: {
      name: "后端协作者",
      role: "任务与接口",
      mode: "智能体",
      note: "负责任务、审批和交接流。",
    },
  },
  {
    label: "实验室联络",
    draft: {
      name: "实验室联络",
      role: "硬件与真机",
      mode: "人类",
      note: "负责接线、烧录、测量和安全确认。",
    },
  },
];

export const SEED_COLLABORATORS: Collaborator[] = [
  {
    id: "human-chief",
    name: "总工程师",
    kind: "人类",
    role: "项目主理",
    computer: "主控机",
    status: "在线",
    currentTask: "确认范围和验收路径",
    skills: ["决策", "审查", "安全确认"],
    note: "负责最终确认和真机操作。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "ai-fe",
    name: "前端协作者",
    kind: "智能体",
    role: "页面与交互",
    computer: "前端机",
    status: "工作中",
    currentTask: "登录页和协作者页",
    skills: ["页面", "表单", "本机草稿"],
    note: "优先处理入口和编辑流程。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "ai-be",
    name: "后端协作者",
    kind: "智能体",
    role: "任务与接口",
    computer: "后端机",
    status: "待确认",
    currentTask: "接任务、审批、交接",
    skills: ["任务流", "审批", "审计"],
    note: "先补闭环，再接真实接口。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "ai-lab",
    name: "实验室联络",
    kind: "智能体",
    role: "硬件与真机",
    computer: "实验机",
    status: "待接手",
    currentTask: "实验室风险闸门",
    skills: ["真机", "烧录", "日志"],
    note: "硬件动作必须由人类确认。",
    enabled: false,
    updatedAt: new Date().toISOString(),
  },
];

export const SEED_MEMBERS: Member[] = [
  {
    id: "human-chief",
    name: "总工程师",
    email: "human-chief@local",
    kind: "人类",
    role: "项目主理",
    project: DEFAULT_PROJECT,
    thread: "主控线程",
    computer: "主控机",
    status: "在线",
    note: "负责最终确认、真机操作和验收。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "ai-fe",
    name: "前端协作者",
    email: "fe@local",
    kind: "智能体",
    role: "页面与交互",
    project: DEFAULT_PROJECT,
    thread: "AI-FE-LEAD",
    computer: "前端机",
    status: "工作中",
    note: "优先处理入口、编辑流程和可视化。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "ai-be",
    name: "后端协作者",
    email: "be@local",
    kind: "智能体",
    role: "任务与接口",
    project: DEFAULT_PROJECT,
    thread: "AI-BE-LEAD",
    computer: "后端机",
    status: "待确认",
    note: "优先处理任务、审批和交接。",
    enabled: true,
    updatedAt: new Date().toISOString(),
  },
];

export const SEED_INVITATIONS: Invitation[] = [
  {
    id: "invite-lab",
    email: "lab@local",
    name: "实验室联络",
    project: DEFAULT_PROJECT,
    role: "硬件与真机",
    thread: "AI-LAB",
    note: "负责实验室风险和真机确认。",
    status: "待发送",
    createdAt: new Date().toISOString(),
  },
];

export function createLoginDraft(overrides?: Partial<LoginDraft>): LoginDraft {
  return {
    id: overrides?.id ?? `session-${Date.now()}`,
    name: overrides?.name ?? "",
    role: overrides?.role ?? "",
    project: overrides?.project ?? "",
    computer: overrides?.computer ?? "",
    thread: overrides?.thread ?? "",
    mode: overrides?.mode ?? "人类",
    note: overrides?.note ?? "",
    remember: overrides?.remember ?? true,
    updatedAt: overrides?.updatedAt ?? new Date().toISOString(),
  };
}

export function createCollaborator(overrides?: Partial<Collaborator>): Collaborator {
  return {
    id: overrides?.id ?? `collab-${Date.now()}`,
    name: overrides?.name ?? "",
    kind: overrides?.kind ?? "智能体",
    role: overrides?.role ?? "",
    computer: overrides?.computer ?? "",
    status: overrides?.status ?? "待确认",
    currentTask: overrides?.currentTask ?? "",
    skills: overrides?.skills ?? [],
    note: overrides?.note ?? "",
    enabled: overrides?.enabled ?? true,
    updatedAt: overrides?.updatedAt ?? new Date().toISOString(),
  };
}

export function createMember(overrides?: Partial<Member>): Member {
  return {
    id: overrides?.id ?? `member-${Date.now()}`,
    name: overrides?.name ?? "",
    email: overrides?.email ?? "",
    kind: overrides?.kind ?? "智能体",
    role: overrides?.role ?? "",
    project: overrides?.project ?? "",
    thread: overrides?.thread ?? "",
    computer: overrides?.computer ?? "",
    status: overrides?.status ?? "待确认",
    note: overrides?.note ?? "",
    enabled: overrides?.enabled ?? true,
    updatedAt: overrides?.updatedAt ?? new Date().toISOString(),
  };
}

export function createInvitation(overrides?: Partial<Invitation>): Invitation {
  return {
    id: overrides?.id ?? `invite-${Date.now()}`,
    email: overrides?.email ?? "",
    name: overrides?.name ?? "",
    project: overrides?.project ?? "",
    role: overrides?.role ?? "",
    thread: overrides?.thread ?? "",
    note: overrides?.note ?? "",
    status: overrides?.status ?? "待发送",
    createdAt: overrides?.createdAt ?? new Date().toISOString(),
  };
}

export function readJSON<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJSON(key: string, value: unknown) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function formatTime(value: string) {
  if (!value) return "刚刚";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function splitTags(value: string) {
  return value
    .split(/[，,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function tagsToText(tags: string[]) {
  return tags.join("，");
}

export function loginDraftToCollaborator(login: LoginDraft | null): Collaborator {
  if (!login) return createCollaborator();
  return createCollaborator({
    id: `login-${login.id}`,
    name: login.name || "登录身份",
    kind: login.mode === "人类" ? "人类" : "智能体",
    role: login.role || "待补充",
    computer: login.computer || "未填写",
    status: login.mode === "观察者" ? "待确认" : "在线",
    currentTask: login.thread || login.project || "等待分配",
    skills: splitTags(login.note || "登录页导入"),
    note: login.note || "从登录页导入。",
    enabled: true,
    updatedAt: login.updatedAt || new Date().toISOString(),
  });
}

export function loginDraftToMember(login: LoginDraft | null): Member | null {
  if (!login) return null;
  return createMember({
    id: `login-${login.id}`,
    name: login.name || "登录身份",
    email: `${login.id}@local`,
    kind: login.mode === "人类" ? "人类" : "智能体",
    role: login.role || "待补充",
    project: login.project || DEFAULT_PROJECT,
    thread: login.thread || "待分配",
    computer: login.computer || "未填写",
    status: login.mode === "观察者" ? "待确认" : "在线",
    note: login.note || "从登录页导入。",
    updatedAt: login.updatedAt || new Date().toISOString(),
  });
}

export function collaboratorToMember(item: Collaborator): Member {
  return createMember({
    id: `member-${item.id}`,
    name: item.name,
    email: `${item.id}@local`,
    kind: item.kind,
    role: item.role,
    project: DEFAULT_PROJECT,
    thread: item.currentTask || item.role,
    computer: item.computer,
    status: item.enabled ? (item.status === "离线" ? "离线" : item.status === "待接手" ? "待确认" : "工作中") : "离线",
    note: item.note,
    enabled: item.enabled,
    updatedAt: item.updatedAt,
  });
}

export function apiUserToMember(user: any): Member {
  return createMember({
    id: String(user.id ?? user.email ?? `user-${Date.now()}`),
    name: String(user.name ?? user.display_name ?? user.email ?? "未命名"),
    email: String(user.email ?? `${user.id ?? "user"}@local`),
    kind: "人类",
    role: String(user.global_role ?? "member"),
    project: DEFAULT_PROJECT,
    thread: String(user.display_name ?? user.bio ?? "后端名册"),
    computer: "后端名册",
    status: user.is_active === false ? "离线" : "在线",
    note: String(user.notes ?? user.bio ?? "来自后端用户列表。"),
    enabled: user.is_active !== false,
    updatedAt: String(user.updated_at ?? new Date().toISOString()),
  });
}

export function apiInvitationToInvitation(item: any): Invitation {
  return createInvitation({
    id: String(item.id ?? `invite-${Date.now()}`),
    email: String(item.email ?? ""),
    name: String(item.name ?? item.email ?? "未命名邀请"),
    project: String(item.project?.name ?? item.project?.id ?? item.project_id ?? DEFAULT_PROJECT),
    role: String(item.role ?? "collaborator"),
    thread: String(item.thread ?? item.role ?? "待分配"),
    note: String(item.note ?? item.project?.name ?? "来自后端邀请队列。"),
    status:
      item.status === "accepted"
        ? "已接受"
        : item.status === "rejected"
          ? "已拒绝"
          : item.status === "pending"
            ? "待接受"
            : "待发送",
    createdAt: String(item.created_at ?? new Date().toISOString()),
  });
}

