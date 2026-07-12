import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../../lib/config";

const ACCESS_TOKEN_COOKIE = "farm_access_token";

const PLATFORM_RECOMMENDED_PROJECT_SKILLS: Record<string, { label: string; note: string; recommendedFor: string[] }> = {
  "platform-boss-planning": {
    label: "平台 Boss 分工规划",
    note: "把用户的一句话需求拆成可执行方案、工位分工、NPC 职责、GitHub 知识库路径和验收口径；Boss 只做规划、派单、收口，不直接替执行 NPC 写实现。",
    recommendedFor: ["Boss NPC", "产品与分工工位", "项目负责人"],
  },
  "platform-backend-api": {
    label: "平台后端接口与数据",
    note: "负责阅读项目仓库文档，梳理接口、数据模型、数据流、导出格式和迁移风险；输出要能被前端和 QA NPC 复用。",
    recommendedFor: ["后端数据 NPC", "标注与导出工位"],
  },
  "platform-frontend-workbench": {
    label: "平台前端工作台体验",
    note: "负责从真实用户路径检查页面密度、主操作、工作台布局和状态反馈；提交前必须说明点击步骤和页面状态。",
    recommendedFor: ["前端体验 NPC", "工作台体验工位"],
  },
  "platform-dataset-export": {
    label: "平台数据集导出",
    note: "关注音频、文本、评分、标注结果的导入导出闭环；每次改动要说明字段来源、兼容旧数据方式和可回滚点。",
    recommendedFor: ["后端数据 NPC", "数据治理 NPC"],
  },
  "platform-browser-acceptance": {
    label: "平台浏览器验收",
    note: "用用户视角验证页面能不能用、密度是否舒服、核心按钮是否找得到；每次给出截图或明确的路由、操作、结果。",
    recommendedFor: ["QA 验收 NPC", "验收风险工位"],
  },
  "platform-cross-station-routing": {
    label: "跨工位协作路由",
    note: "同一工位 NPC 互相认识并按职责找人；不同工位只能通过目标工位长 NPC 沟通，回执必须回到发起 NPC 和 Boss 收口。",
    recommendedFor: ["Boss NPC", "工位长 NPC", "协作平台 NPC"],
  },
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function safeReturnTo(projectId: string, value: unknown) {
  const raw = text(value, "");
  const fallback = `/projects/${encodeURIComponent(projectId)}/2d-upgrade?panel=skills&action=skill-category`;
  if (!raw.startsWith(`/projects/${projectId}/`)) return fallback;
  return raw;
}

function withResult(path: string, key: "team_notice" | "team_error", message: string, requestUrl: string) {
  const origin = new URL(requestUrl).origin;
  const url = new URL(path, origin);
  url.searchParams.set(key, message);
  return url;
}

function normalizeSkillId(value: unknown) {
  return text(value, "")
    .toLowerCase()
    .replace(/[^a-z0-9-_]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

async function readUpstreamJson(path: string, token: string) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
  return json?.data ?? json;
}

async function patchUpstreamJson(path: string, token: string, body: Record<string, unknown>) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.error?.message ?? `HTTP ${res.status}`);
  return json?.data ?? json;
}

export async function POST(request: Request, ctx: { params: { id: string } }) {
  const projectId = ctx.params.id;
  const formData = await request.formData();
  const returnTo = safeReturnTo(projectId, formData.get("return_to"));
  try {
    const token = cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? "";
    if (!token) throw new Error("登录态已过期，请重新登录后再创建 Skill。");
    const skillId = normalizeSkillId(formData.get("skill_id"));
    const preset = PLATFORM_RECOMMENDED_PROJECT_SKILLS[skillId];
    if (!preset) throw new Error("没有找到这个推荐 Skill。");

    const project = await readUpstreamJson(`/api/projects/${encodeURIComponent(projectId)}`, token);
    const collaborationConfig =
      project?.collaboration_config && typeof project.collaboration_config === "object"
        ? { ...(project.collaboration_config as Record<string, unknown>) }
        : {};
    const skillLibrary = Array.isArray(collaborationConfig.skill_library)
      ? [...(collaborationConfig.skill_library as Record<string, unknown>[])]
      : [];
    if (skillLibrary.some((item) => normalizeSkillId(item.id) === skillId)) {
      return NextResponse.redirect(withResult(returnTo, "team_notice", `Skill 已存在：${preset.label}`, request.url));
    }
    const nextSkill = {
      id: skillId,
      label: preset.label,
      note: preset.note,
      source: "custom",
      scope: "role",
      recommended_for: preset.recommendedFor,
    };
    const nextLibrary = [...skillLibrary, nextSkill].sort((left, right) =>
      text(left.label ?? left.id).localeCompare(text(right.label ?? right.id), "zh-CN"),
    );
    await patchUpstreamJson(`/api/projects/${encodeURIComponent(projectId)}`, token, {
      collaboration_config: {
        ...collaborationConfig,
        skill_library: nextLibrary,
      },
    });
    return NextResponse.redirect(withResult(returnTo, "team_notice", `已新增 Skill：${preset.label}`, request.url));
  } catch (error) {
    return NextResponse.redirect(
      withResult(returnTo, "team_error", error instanceof Error ? error.message : "推荐 Skill 创建失败", request.url),
    );
  }
}
