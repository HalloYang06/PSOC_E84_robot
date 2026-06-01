"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { 创建项目Skill, 删除能力工坊知识库, 删除项目Skill, 启用Npc自造Skill, 导入Github项目Skill, 保存能力工坊知识库, 添加Skill到Npc, 索引Npc沉淀, 绑定知识库到Npc } from "../../../actions";
import { recommendRoleSkillIds } from "../../../../lib/platform-skills";
import tileStyles from "../workbench/_components/npc-tile.module.css";
import workbenchStyles from "../workbench/workbench.module.css";
import styles from "./skill-forge.module.css";

type AnyRecord = Record<string, any>;
type ForgeTab = "skills" | "knowledge" | "git";
type ForgeResource = {
  id: string;
  kind: "station" | "seat";
  name: string;
  seatRowId?: string;
  seatConfigId?: string;
  parentId?: string;
  parentName?: string;
};

type CollaborationSeed = {
  source?: string;
  needId?: string;
  taskId?: string;
  dispatchId?: string;
  rawNeedId?: string;
  rawTaskId?: string;
  rawDispatchId?: string;
  title?: string;
  summary?: string;
  output?: string;
  receipt?: string;
} | null;

type SkillForgeClientProps = {
  projectId: string;
  projectName: string;
  projectRepo: string;
  returnTo?: string;
  returnToLabel?: string;
  surfaceNotice?: string;
  surfaceError?: string;
  skills: AnyRecord[];
  documents: AnyRecord[];
  assignments: AnyRecord[];
  messages: AnyRecord[];
  seats: AnyRecord[];
  workstations: AnyRecord[];
  initialOpenResourceIds: string[];
  initialActiveTab?: ForgeTab;
  initialCollaborationSeed?: CollaborationSeed;
};

function text(value: unknown, fallback = "") {
  const next = String(value ?? "").trim();
  return next || fallback;
}

function userMessage(value: unknown, fallback = "") {
  const decoded = text(value, fallback).replace(/\+/g, " ");
  let next = decoded;
  try {
    next = decodeURIComponent(decoded);
  } catch {
    next = decoded;
  }
  if (/"kind"\s*:\s*"codex\.desktop\.dispatch"/i.test(next) || /\bcodex\.desktop\.dispatch\b/i.test(next)) {
    return "执行电脑已登记桌面后台接收请求；平台会等待桌面线程确认和最终结果。";
  }
  return next
    .replace(/已把这条派单送进绑定桌面线程；完整处理过程在桌面版继续。平台正在等待桌面线程写出最终回复。/gi, "执行电脑已登记桌面后台接收请求；不会抢占当前窗口，平台等待桌面线程确认后继续同步最终结果。")
    .replace(/\bRunner\s+([A-Za-z0-9._-]+)\s+received platform dispatch:?/gi, "执行电脑 $1 已收到平台派单：")
    .replace(/\bRunner\s+已收到云端派单，正在回写最小回执。/gi, "执行电脑已收到云端派单，正在等待桌面确认。")
    .replace(/目标 NPC 已接到平台派单：\s*[0-9a-f-]{16,}/gi, "目标 NPC 已接到平台派单")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "关联记录")
    .replace(/处理方式：桌面线程处理中。/gi, "处理方式：桌面后台处理中。")
    .replace(/工作区：待绑定工作区。/gi, "")
    .replace(/平台会继续同步最小回执、待收口状态和最终结果。/gi, "平台会继续同步已收到提醒、等待结果状态和最终结果。")
    .replace(/最小回执/gi, "已收到提醒")
    .replace(/待收口/gi, "等结果")
    .replace(/\bfinal\b/gi, "最终结果")
    .replace(/抢占式引导/gi, "桌面提醒")
    .replace(/\bknowledge\.[a-z_.-]+\b/gi, "能力治理")
    .replace(/\bproject\.[a-z_.-]+\b/gi, "项目治理")
    .replace(/\bseat[_-]?skill[_-]?assignments?\b/gi, "能力绑定")
    .replace(/\bthread[_-]?workstations?\b/gi, "NPC 坐席")
    .replace(/\badapter\b/gi, "同步")
    .replace(/\bbridge\b/gi, "同步")
    .replace(/\bsession JSONL\b/gi, "线程记录")
    .trim() || fallback;
}

function idOf(value: AnyRecord) {
  return text(value.id ?? value.workstation_id ?? value.config_id ?? value.row_id ?? value.slug, "");
}

function seatIdentityValues(value: AnyRecord) {
  return [
    value.row_id,
    value.rowId,
    value.id,
    value.config_id,
    value.configId,
    value.name,
  ].map((item) => text(item, "")).filter(Boolean);
}

function seatMatchesResource(value: AnyRecord, resource: ForgeResource) {
  if (resource.kind !== "seat") return false;
  const identities = seatIdentityValues(value);
  return [resource.seatRowId, resource.id, resource.seatConfigId]
    .filter((identity): identity is string => Boolean(identity))
    .some((identity) => identities.includes(identity));
}

function nameOf(value: AnyRecord, fallback: string) {
  return text(value.name ?? value.label ?? value.title, fallback);
}

function workstationIdOfSeat(value: AnyRecord) {
  return text(value.workstation_id ?? value.workstationId ?? value.development_station_id ?? value.metadata?.workstation_id, "");
}

function seatResponsibilityOf(value: AnyRecord | null | undefined) {
  const metadata = metadataOf(value ?? {});
  const extraData = value?.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  return text(
    value?.responsibility ??
      value?.description ??
      value?.notes ??
      metadata.responsibility ??
      metadata.role ??
      extraData.responsibility ??
      extraData.role,
    "",
  );
}

function skillIdOf(value: AnyRecord) {
  return text(value.skill_id ?? value.skillId ?? value.id ?? value.slug, "").toLowerCase();
}

function skillLabelOf(value: AnyRecord, fallback = "Skill") {
  return userMessage(value.label ?? value.name ?? value.title ?? value.skill_id ?? value.id, fallback);
}

function skillDescriptionOf(value: AnyRecord) {
  return userMessage(value.description ?? value.note ?? value.summary, "");
}

function skillSourceLabel(value: AnyRecord) {
  const meta = metadataOf(value);
  const source = text(value.source ?? value.category ?? meta.imported_from, "项目 Skill");
  if (/platform|baseline|role/i.test(source)) return "平台基础";
  if (/npc|agent/i.test(source)) return "NPC 自己创建";
  if (/local/i.test(source)) return "用户导入本地 Skill";
  if (/github|repo/i.test(source)) return "用户导入 GitHub 路径";
  if (/human|custom/i.test(source)) return "用户手动创建";
  return source;
}

function skillRepoPathOf(value: AnyRecord) {
  const meta = metadataOf(value);
  return text(value.repo_relative_path ?? value.repoRelativePath ?? value.path ?? meta.repo_relative_path ?? meta.external_path, "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
}

function githubRepoPathHref(projectRepo: string, repoPath: string) {
  const normalizedPath = text(repoPath, "").replace(/^\/+/, "");
  if (!normalizedPath) return "";
  const repo = text(projectRepo, "");
  if (!repo || repo === "待绑定 GitHub 仓库") return "";
  const mode = normalizedPath.endsWith("/") ? "tree" : "blob";
  if (/^https:\/\/github\.com\/[^/]+\/[^/]+/i.test(repo)) {
    const cleanRepo = repo.replace(/\.git$/i, "").replace(/\/+$/, "");
    return `${cleanRepo}/${mode}/main/${normalizedPath}`;
  }
  const ssh = repo.match(/^git@github\.com:([^/]+\/[^/]+?)(?:\.git)?$/i);
  if (ssh) return `https://github.com/${ssh[1].replace(/\.git$/i, "")}/${mode}/main/${normalizedPath}`;
  return "";
}

function githubBlobHref(projectRepo: string, repoPath: string) {
  return githubRepoPathHref(projectRepo, repoPath);
}

function githubRepoHref(projectRepo: string) {
  const repo = text(projectRepo, "");
  if (!repo || repo === "待绑定 GitHub 仓库") return "";
  if (/^https:\/\/github\.com\/[^/]+\/[^/]+/i.test(repo)) return repo.replace(/\.git$/i, "").replace(/\/+$/, "");
  const ssh = repo.match(/^git@github\.com:([^/]+\/[^/]+?)(?:\.git)?$/i);
  if (ssh) return `https://github.com/${ssh[1].replace(/\.git$/i, "")}`;
  return "";
}

function externalSkillHref(value: AnyRecord) {
  const meta = metadataOf(value);
  return text(meta.source_url ?? meta.html_url ?? meta.raw_url, "");
}

function isBuiltInSkill(value: AnyRecord) {
  const source = text(value.source, "").toLowerCase();
  const scope = text(value.scope, "").toLowerCase();
  return source.startsWith("platform-") || scope === "baseline" || value.required === true;
}

function assignmentStatusOf(value: AnyRecord | null | undefined) {
  return text(value?.status ?? value?.state ?? value?.extra_data?.status ?? value?.extraData?.status, "").toLowerCase();
}

function skillDraftStatusOf(value: AnyRecord) {
  const meta = metadataOf(value);
  return text(
    value.draft_status ??
      value.draftStatus ??
      value.status ??
      meta.draft_status ??
      meta.draftStatus,
    "",
  ).toLowerCase();
}

function isActiveAssignment(value: AnyRecord | null | undefined) {
  const status = assignmentStatusOf(value);
  return !status || status === "active" || status === "enabled";
}

function isDraftLikeStatus(value: string) {
  return /draft|pending|review|ready|test|testing/i.test(value);
}

function roleSkillLoadoutOf(value: AnyRecord) {
  const metadata = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
  const raw = value.skill_loadout ?? value.skillLoadout ?? metadata.skill_loadout ?? metadata.additional_skill_ids;
  const list = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(/[\n,]/) : [];
  return list.map((item) => text(item).toLowerCase()).filter(Boolean);
}

function knowledgePathsOf(value: AnyRecord) {
  const metadata = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
  const extraData = value.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  const raw = value.knowledge_paths ?? value.knowledgePaths ?? metadata.knowledge_paths ?? metadata.knowledgePaths ?? extraData.knowledge_paths;
  const list = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(/[\n,]/) : [];
  return list.map((item) => text(item).replace(/\\/g, "/").replace(/^\/+/, "")).filter(Boolean);
}

function seatParentId(value: AnyRecord) {
  const metadata = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
  const extraData = value.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  return text(
    value.workstation_id ??
      value.workstationId ??
      value.development_station_id ??
      value.developmentStationId ??
      metadata.workstation_id ??
      metadata.workstationId ??
      metadata.development_station_id ??
      metadata.developmentStationId ??
      extraData.workstation_id ??
      extraData.development_station_id,
    "",
  );
}

function resourceKey(resource: ForgeResource) {
  return `${resource.kind}:${resource.id}`;
}

function uniqueIds(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    const id = text(value, "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function resourceLabel(resource: ForgeResource) {
  return resource.kind === "seat" ? "NPC" : "工位";
}

function matchesAssignment(assignment: AnyRecord, resource: ForgeResource) {
  if (resource.kind === "seat") {
    const assignedTo = text(assignment.seat_id ?? assignment.seatId ?? assignment.npc_id ?? assignment.agent_id, "");
    return [resource.seatRowId, resource.id, resource.seatConfigId].filter(Boolean).includes(assignedTo);
  }
  return text(assignment.workstation_id ?? assignment.workstationId ?? assignment.station_id, "") === resource.id;
}

function matchesKnowledge(doc: AnyRecord, resource: ForgeResource) {
  const haystack = `${text(doc.owner_id ?? doc.ownerId ?? doc.seat_id ?? doc.workstation_id, "")} ${text(doc.title ?? doc.name, "")} ${text(doc.path ?? doc.repo_relative_path ?? doc.repoRelativePath, "")}`.toLowerCase();
  return haystack.includes(resource.id.toLowerCase()) || (resource.parentId ? haystack.includes(resource.parentId.toLowerCase()) : false);
}

function docKeyOf(doc: AnyRecord, index = 0) {
  return text(doc.id ?? doc.repo_relative_path ?? doc.repoRelativePath ?? doc.path ?? doc.title, `doc-${index}`);
}

function docPathOf(doc: AnyRecord) {
  return text(doc.repo_relative_path ?? doc.repoRelativePath ?? doc.path, "").replace(/\\/g, "/").replace(/^\/+/, "");
}

function docSourceLabel(value: AnyRecord) {
  const metadata = value.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  const source = text(metadata.source ?? value.source ?? value.scope, "知识库");
  if (/npc|agent/i.test(source)) return "NPC 自己创建";
  if (/local/i.test(source)) return "用户导入本地知识库";
  if (/github|repo/i.test(source)) return "用户导入 GitHub 路径";
  if (/human|custom/i.test(source)) return "用户手动创建";
  if (/workstation|station/i.test(source)) return "工位继承";
  return source;
}

function metadataOf(value: AnyRecord) {
  const meta = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
  const extra = value.extra_data && typeof value.extra_data === "object" ? value.extra_data : {};
  return { ...extra, ...meta };
}

function slugifyPathSegment(value: unknown, fallback = "npc") {
  return text(value, fallback)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || fallback;
}

function npcKnowledgeOf(seat?: AnyRecord | null) {
  const meta = metadataOf(seat ?? {});
  return meta.npc_knowledge && typeof meta.npc_knowledge === "object" ? (meta.npc_knowledge as AnyRecord) : {};
}

function npcDepositPaths(seat: AnyRecord | null | undefined, resource: ForgeResource) {
  const knowledge = npcKnowledgeOf(seat);
  const slug = slugifyPathSegment(knowledge.slug ?? resource.name ?? resource.id, "npc");
  return {
    knowledge: text(knowledge.knowledge_deposit_path, `docs/npc-knowledge/${slug}/`),
    skill: text(knowledge.skill_deposit_path, `skills/npc-authored/${slug}/`),
    need: text(knowledge.need_deposit_path, `docs/npc-requests/${slug}/needs/`),
    task: text(knowledge.task_deposit_path, `docs/npc-requests/${slug}/tasks/`),
  };
}

function workstationKnowledgePlaceholder(resource: ForgeResource) {
  return `docs/workstations/${slugifyPathSegment(resource.name || resource.id, "workstation")}.md`;
}

function stringValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap((item) => stringValues(item));
  if (value && typeof value === "object") return Object.values(value as AnyRecord).flatMap((item) => stringValues(item));
  const next = text(value, "");
  return next ? [next] : [];
}

function isGitMessage(value: AnyRecord) {
  const meta = metadataOf(value);
  const haystack = [
    value.message_type,
    value.messageType,
    value.title,
    value.body,
    meta.source,
    meta.kind,
    meta.git_event,
    meta.git_action,
    meta.git_operation,
    meta.rollback_preview,
    meta.sync_preview,
  ].map((item) => text(item, "").toLowerCase()).join(" ");
  return /(^|[^a-z])git([^a-z]|$)|github|rollback|回退|提交|分支|pr|pull request|预检|同步/.test(haystack);
}

function messageBelongsToResource(value: AnyRecord, resource: ForgeResource, childSeatIds: string[] = []) {
  if (!isGitMessage(value)) return false;
  const meta = metadataOf(value);
  const directIds = new Set([resource.id, ...childSeatIds].filter(Boolean));
  if (directIds.has(text(value.sender_id ?? value.senderId, "")) || directIds.has(text(value.recipient_id ?? value.recipientId, ""))) {
    return true;
  }
  const related = stringValues({
    author_seat_id: meta.author_seat_id,
    seat_id: meta.seat_id,
    npc_id: meta.npc_id,
    target_seat_id: meta.target_seat_id,
    affected_seat_id: meta.affected_seat_id,
    affected_seat_ids: meta.affected_seat_ids,
    reviewer_seat_id: meta.reviewer_seat_id,
    assignee_seat_id: meta.assignee_seat_id,
    workstation_id: meta.workstation_id,
    station_id: meta.station_id,
  });
  return related.some((item) => directIds.has(item));
}

function messageTime(value: AnyRecord) {
  const raw = text(value.created_at ?? value.createdAt, "");
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function snapshotTime(value: unknown) {
  const raw = text(value, "");
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function forgeHref(projectId: string, openIds: string[]) {
  const params = new URLSearchParams();
  if (openIds.length) params.set("resources", openIds.join(","));
  const suffix = params.toString();
  return `/projects/${projectId}/skill-forge${suffix ? `?${suffix}` : ""}`;
}

function ForgeTile({
  projectId,
  projectRepo,
  resource,
  sourceSeat,
  openIds,
  skills,
  documents,
  assignments,
  messages,
  seats,
  onClose,
  initialActiveTab = "skills",
  collaborationSeed = null,
}: {
  projectId: string;
  projectRepo: string;
  resource: ForgeResource;
  sourceSeat?: AnyRecord | null;
  openIds: string[];
  skills: AnyRecord[];
  documents: AnyRecord[];
  assignments: AnyRecord[];
  messages: AnyRecord[];
  seats: AnyRecord[];
  onClose: () => void;
  initialActiveTab?: ForgeTab;
  collaborationSeed?: CollaborationSeed;
}) {
  const [activeTab, setActiveTab] = useState<ForgeTab>(initialActiveTab);
  const focusedAssignments = assignments.filter((assignment) => matchesAssignment(assignment, resource));
  const assignmentBySkillId = new Map(focusedAssignments.map((assignment) => [skillIdOf(assignment), assignment]));
  const boundKnowledgePaths = new Set(resource.kind === "seat" && sourceSeat ? knowledgePathsOf(sourceSeat) : []);
  const focusedKnowledge = documents.filter((doc) => matchesKnowledge(doc, resource) || boundKnowledgePaths.has(docPathOf(doc)));
  const activeAssignedSkillIds = new Set([
    ...focusedAssignments.filter(isActiveAssignment).map(skillIdOf),
    ...(resource.kind === "seat" && sourceSeat ? roleSkillLoadoutOf(sourceSeat) : []),
  ].filter(Boolean));
  const configuredSkillIds = new Set([
    ...focusedAssignments.map(skillIdOf),
    ...(resource.kind === "seat" && sourceSeat ? roleSkillLoadoutOf(sourceSeat) : []),
  ].filter(Boolean));
  const orderedSkills = [...skills].sort((left, right) => {
    const leftBuiltIn = isBuiltInSkill(left) ? 1 : 0;
    const rightBuiltIn = isBuiltInSkill(right) ? 1 : 0;
    if (leftBuiltIn !== rightBuiltIn) return leftBuiltIn - rightBuiltIn;
    const leftAssigned = configuredSkillIds.has(skillIdOf(left)) ? 0 : 1;
    const rightAssigned = configuredSkillIds.has(skillIdOf(right)) ? 0 : 1;
    if (leftAssigned !== rightAssigned) return leftAssigned - rightAssigned;
    return skillLabelOf(left).localeCompare(skillLabelOf(right), "zh-Hans-CN");
  });
  const assignedSkills = orderedSkills.filter((skill) => configuredSkillIds.has(skillIdOf(skill)) || isBuiltInSkill(skill));
  const availableSkills = orderedSkills.filter((skill) => !assignedSkills.includes(skill));
  const recommendedSkillIds = resource.kind === "seat"
    ? recommendRoleSkillIds({
        roleText: `${resource.name} ${resource.parentName || ""} ${seatResponsibilityOf(sourceSeat)}`,
        threadText: `${text(sourceSeat?.provider_label ?? sourceSeat?.providerLabel ?? sourceSeat?.ai_provider_id, "")} ${text(sourceSeat?.model, "")}`,
        skillLibrary: skills,
        limit: 5,
      }).filter((skillId) => !configuredSkillIds.has(skillId.toLowerCase()))
    : [];
  const recommendedSkills = recommendedSkillIds
    .map((skillId) => orderedSkills.find((skill) => skillIdOf(skill) === skillId.toLowerCase()))
    .filter((skill): skill is AnyRecord => Boolean(skill));
  const roleSkillCount = resource.kind === "seat" ? activeAssignedSkillIds.size : focusedAssignments.filter(isActiveAssignment).length;
  const pendingSkillCount = resource.kind === "seat"
    ? assignedSkills.filter((skill) => {
        const id = skillIdOf(skill);
        if (isBuiltInSkill(skill) || activeAssignedSkillIds.has(id)) return false;
        const assignment = assignmentBySkillId.get(id);
        return isDraftLikeStatus(assignmentStatusOf(assignment)) || isDraftLikeStatus(skillDraftStatusOf(skill));
      }).length
    : 0;
  const skillSnapshot = (sourceSeat?.metadata?.skill_forge_snapshot ?? sourceSeat?.extra_data?.skill_forge_snapshot ?? null) as AnyRecord | null;
  const knowledgeSnapshot = (sourceSeat?.metadata?.knowledge_forge_snapshot ?? sourceSeat?.extra_data?.knowledge_forge_snapshot ?? null) as AnyRecord | null;
  const runtimeSnapshots = [
    skillSnapshot
      ? {
          id: "skill",
          label: text(skillSnapshot.changed_skill_label, text(skillSnapshot.changed_skill_id, "Skill 配置已更新")),
          owner: text(skillSnapshot.affected_seat_name ?? skillSnapshot.seat_name, resource.name),
          generatedAt: snapshotTime(skillSnapshot.generated_at ?? skillSnapshot.updated_at ?? skillSnapshot.activated_at),
          effect: text(skillSnapshot.effect, "下一轮派单 / 刷新后的上岗包会读取"),
          source: text(skillSnapshot.source, "能力工坊"),
          summary: text(skillSnapshot.summary, "Skill 配置已同步到该 NPC。"),
        }
      : null,
    knowledgeSnapshot
      ? {
          id: "knowledge",
          label: text(knowledgeSnapshot.changed_title ?? knowledgeSnapshot.changed_path, "知识库配置已更新"),
          owner: text(knowledgeSnapshot.affected_seat_name ?? knowledgeSnapshot.seat_name, resource.name),
          generatedAt: snapshotTime(knowledgeSnapshot.generated_at ?? knowledgeSnapshot.updated_at ?? knowledgeSnapshot.activated_at),
          effect: text(knowledgeSnapshot.effect, "下一轮派单 / 刷新后的上岗包会读取"),
          source: text(knowledgeSnapshot.source, "能力工坊"),
          summary: text(knowledgeSnapshot.summary, "知识库配置已同步到该 NPC。"),
        }
      : null,
  ].filter((item): item is { id: string; label: string; owner: string; generatedAt: string; effect: string; source: string; summary: string } => Boolean(item));
  const deposits = resource.kind === "seat" ? npcDepositPaths(sourceSeat, resource) : null;
  const tabLabel = activeTab === "knowledge" ? "知识库配置" : activeTab === "git" ? "Git 管理" : "Skill 配置";
  const seedTitle = text(collaborationSeed?.title, `${resource.name} 协作沉淀`);
  const seedSummary = [
    collaborationSeed?.summary ? `协作摘要：${collaborationSeed.summary}` : "",
    collaborationSeed?.output ? `期望产出：${collaborationSeed.output}` : "",
    collaborationSeed?.receipt ? `最新回执：${collaborationSeed.receipt}` : "",
  ].filter(Boolean).join("\n");
  const seedSlug = slugifyPathSegment(seedTitle, "collaboration-note");
  const seedReturnPath = `/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}&tab=${activeTab}`;
  const seedKnowledgePath = deposits
    ? `${deposits.knowledge}${seedSlug}.md`
    : `docs/workstations/${slugifyPathSegment(resource.name || resource.id, "workstation")}/${seedSlug}.md`;
  const seedSkillPath = deposits ? `${deposits.skill}${seedSlug}/SKILL.md` : `skills/custom/${seedSlug}/SKILL.md`;
  const childSeatIds = resource.kind === "station"
    ? seats.filter((seat) => seatParentId(seat) === resource.id).map((seat) => idOf(seat)).filter(Boolean)
    : [];
  const gitMessages = messages
    .filter((message) => messageBelongsToResource(message, resource, childSeatIds))
    .sort((left, right) => text(right.created_at ?? right.createdAt, "").localeCompare(text(left.created_at ?? left.createdAt, "")))
    .slice(0, 8);

  return (
    <article className={tileStyles.tile}>
      <header className={tileStyles.head}>
        <div className={tileStyles.headLeft}>
          <strong className={tileStyles.name}>{resource.name}</strong>
          <small className={tileStyles.subline}>{resourceLabel(resource)} · {resource.parentName || "独立资源"} · {tabLabel}</small>
        </div>
        <div className={tileStyles.headActions}>
          <button type="button" className={tileStyles.closeBtn} onClick={onClose} aria-label={`关闭 ${resource.name}`}>×</button>
        </div>
      </header>
      <nav className={tileStyles.panelTabs} aria-label={`${resource.name} 配置切换`}>
        {[
          ["skills", "Skill 配置", assignedSkills.length],
          ["knowledge", "知识库配置", focusedKnowledge.length],
          ["git", "Git 管理", 0],
        ].map(([tab, label, count]) => (
          <button
            key={String(tab)}
            type="button"
            className={tileStyles.panelTab}
            data-active={activeTab === tab ? "1" : "0"}
            onClick={() => setActiveTab(tab as ForgeTab)}
          >
            <span>{label}</span>
            <strong>{count}</strong>
          </button>
        ))}
      </nav>
      <section className={tileStyles.threadBinding}>
        <span className={tileStyles.threadChip}>{resourceLabel(resource)}</span>
        <span className={tileStyles.threadChip}>{resource.parentName || "独立资源"}</span>
        <span className={tileStyles.threadChip}>上岗包快照</span>
      </section>
      {collaborationSeed ? (
        <section className={styles.collaborationSeedCard} aria-label="协作沉淀建议">
          <div>
            <span>来自公司协作线</span>
            <strong>{seedTitle}</strong>
            <p>{seedSummary || "这条协作已经带入当前 NPC，可继续整理成知识或 Skill。"}</p>
          </div>
          <div>
            {collaborationSeed.needId ? <small>已关联需求</small> : null}
            {collaborationSeed.taskId ? <small>已关联任务</small> : null}
            {collaborationSeed.dispatchId ? <small>已关联投递回执</small> : null}
          </div>
          <div className={styles.collaborationSeedActions}>
            <form action={保存能力工坊知识库.bind(null, projectId)}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}&tab=knowledge`} />
              <input type="hidden" name="scope" value={resource.kind === "seat" ? "npc" : "workstation"} />
              <input type="hidden" name="owner_type" value={resource.kind === "seat" ? "seat" : "workstation"} />
              <input type="hidden" name="owner_id" value={resource.id} />
              {resource.kind === "seat" ? <input type="hidden" name="author_seat_id" value={resource.id} /> : null}
              <input type="hidden" name="title" value={seedTitle} />
              <input type="hidden" name="repo_relative_path" value={seedKnowledgePath} />
              <input type="hidden" name="summary" value={seedSummary || seedTitle} />
              <input type="hidden" name="tags" value="collaboration,closure,npc" />
              <input type="hidden" name="closure_source" value="company_collaboration" />
              <input type="hidden" name="closure_need_id" value={text(collaborationSeed.rawNeedId, "")} />
              <input type="hidden" name="closure_task_id" value={text(collaborationSeed.rawTaskId, "")} />
              <input type="hidden" name="closure_dispatch_id" value={text(collaborationSeed.rawDispatchId, "")} />
              <button type="submit">一键保存知识</button>
            </form>
            {resource.kind === "seat" ? (
              <form action={创建项目Skill.bind(null, projectId)}>
                <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}&tab=skills`} />
                <input type="hidden" name="assignment_seat_id" value={resource.seatRowId || resource.id} />
                <input type="hidden" name="author_seat_id" value={resource.seatRowId || resource.id} />
                <input type="hidden" name="source" value="npc-authored" />
                <input type="hidden" name="category" value="npc-authored" />
                <input type="hidden" name="draft_status" value="draft" />
                <input type="hidden" name="skill_id" value={seedSlug} />
                <input type="hidden" name="label" value={seedTitle} />
                <input type="hidden" name="repo_relative_path" value={seedSkillPath} />
                <input type="hidden" name="note" value={seedSummary || seedTitle} />
                <input type="hidden" name="closure_source" value="company_collaboration" />
                <input type="hidden" name="closure_need_id" value={text(collaborationSeed.rawNeedId, "")} />
                <input type="hidden" name="closure_task_id" value={text(collaborationSeed.rawTaskId, "")} />
                <input type="hidden" name="closure_dispatch_id" value={text(collaborationSeed.rawDispatchId, "")} />
                <button type="submit">生成 Skill 草稿</button>
              </form>
            ) : null}
          </div>
        </section>
      ) : null}

      {activeTab === "skills" ? (
        <section className={styles.skillGrid}>
          {resource.kind === "seat" ? (
            <article className={`${styles.editorCard} ${styles.wideCard}`}>
              <span>当前 NPC Skill</span>
              <strong>{assignedSkills.length ? `${resource.name} 已装配 ${assignedSkills.length} 个 Skill` : `${resource.name} 还没有可运行 Skill`}</strong>
              <p>这里先显示该 NPC 当前会带进上岗包的 Skill。来源必须写清楚：NPC 自己创建、用户手动创建、用户导入本地 Skill、用户导入 GitHub 路径；平台基础能力随上岗包生成。</p>
              {deposits ? <small>NPC 默认写入：{deposits.skill}</small> : null}
            </article>
          ) : null}
          {resource.kind === "seat" ? (
            <article className={`${styles.closureCard} ${styles.wideCard}`} data-state={roleSkillCount > 0 && focusedKnowledge.length > 0 ? "ok" : "gap"}>
              <div>
                <span>NPC 能力闭环体检</span>
                <strong>{roleSkillCount > 0 && focusedKnowledge.length > 0 ? "上岗包配置源完整" : "上岗包配置源有缺口"}</strong>
                <p>
                  Skill 会影响 NeedRouter 推荐和 NPC 开工上下文；知识库负责长期事实源。补齐后，新的派单和刷新后的上岗包会读取这里的配置。
                </p>
              </div>
              <div className={styles.closureMetrics}>
                <span data-state={roleSkillCount > 0 ? "ok" : "gap"}><b>{roleSkillCount}</b><small>运行 Skill</small></span>
                <span data-state={pendingSkillCount > 0 ? "gap" : "ok"}><b>{pendingSkillCount}</b><small>待启用</small></span>
                <span data-state={focusedKnowledge.length > 0 ? "ok" : "gap"}><b>{focusedKnowledge.length}</b><small>知识库</small></span>
                <span data-state={runtimeSnapshots.length ? "ok" : "gap"}><b>{runtimeSnapshots.length ? "已刷新" : "待刷新"}</b><small>上岗包</small></span>
              </div>
              {recommendedSkills.length ? (
                <div className={styles.recommendStrip}>
                  <span>建议先补</span>
                  {recommendedSkills.map((skill) => (
                    <form key={`recommended-${skillIdOf(skill)}`} className={styles.inlineAction} action={添加Skill到Npc.bind(null, projectId, resource.seatRowId || resource.id, skillIdOf(skill))}>
                      <input type="hidden" name="return_to" value={seedReturnPath} />
                      <button type="submit">{skillLabelOf(skill)}</button>
                    </form>
                  ))}
                </div>
              ) : roleSkillCount === 0 ? (
                <small>没有命中推荐词；可在下方手动创建或从仓库选择 Skill。</small>
              ) : (
                <small>推荐项已装配或当前职责暂不需要额外 Skill。</small>
              )}
            </article>
          ) : null}
          {(resource.kind === "seat" ? assignedSkills : orderedSkills).map((skill, index) => {
            const builtIn = isBuiltInSkill(skill);
            const skillId = skillIdOf(skill);
            const assignment = assignmentBySkillId.get(skillId);
            const activeInRuntime = activeAssignedSkillIds.has(skillId);
            const draftLike = isDraftLikeStatus(assignmentStatusOf(assignment)) || isDraftLikeStatus(skillDraftStatusOf(skill));
            const statusLabel = builtIn
              ? "平台基础"
              : activeInRuntime
                ? "已进入上岗包"
                : draftLike
                  ? "草稿待确认"
                  : configuredSkillIds.has(skillId)
                    ? "待启用"
                    : "仓库可装配";
            const statusHint = builtIn
              ? "固定基础能力，随上岗包生成。"
              : activeInRuntime
                ? "会进入下一轮派单和刷新后的 NPC 开工上下文。"
                : draftLike
                  ? "只在能力工坊可见，确认前不影响 NPC 当前开工。"
                  : configuredSkillIds.has(skillId)
                    ? "已登记但未作为运行能力启用。"
                    : "添加后才会进入该 NPC 的配置源。";
            const statusState = builtIn ? "baseline" : activeInRuntime ? "active" : draftLike ? "draft" : configuredSkillIds.has(skillId) ? "pending" : "available";
            const repoPath =
              skillRepoPathOf(skill) ||
              text(skill.doc_path, "") ||
              (builtIn ? "apps/web/lib/platform-skills.ts" : "") ||
              (deposits && /npc/i.test(skillSourceLabel(skill)) ? `${deposits.skill}SKILL.md` : "");
            const githubHref = externalSkillHref(skill) || githubBlobHref(projectRepo, repoPath);
            return (
            <article
              key={text(skill.id ?? skill.name, `skill-${index}`)}
              className={`${styles.assetCard} ${activeInRuntime || builtIn ? styles.boundCard : ""}`}
            >
              <div className={styles.cardTopline}>
                <span>{skillSourceLabel(skill)}</span>
                <small data-state={statusState}>{statusLabel}</small>
              </div>
              <strong className={styles.assetTitle}>{skillLabelOf(skill, `Skill ${index + 1}`)}</strong>
              <p className={styles.skillRuntimeHint}>{statusHint}</p>
              <p className={styles.assetDescription}>{skillDescriptionOf(skill) || "暂无说明"}</p>
              <div className={styles.repoLine}>
                <b>{builtIn && !repoPath ? "能力来源" : "仓库位置"}</b>
                {repoPath ? <code>{repoPath}</code> : <em>{builtIn ? "随 NPC 上岗包生成" : "待补仓库路径"}</em>}
                {githubHref ? <a href={githubHref} target="_blank" rel="noreferrer">打开 GitHub</a> : null}
              </div>
              {builtIn ? (
                <small>固定必备</small>
              ) : activeInRuntime ? (
                <small>运行中</small>
              ) : draftLike ? (
                <form className={styles.inlineAction} action={启用Npc自造Skill.bind(null, projectId, skillId)}>
                  <input type="hidden" name="return_to" value={seedReturnPath} />
                  <button type="submit">启用并进入上岗包</button>
                </form>
              ) : resource.kind === "seat" ? (
                <form className={styles.inlineAction} action={添加Skill到Npc.bind(null, projectId, resource.seatRowId || resource.id, skillId)}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?seat=${encodeURIComponent(resource.id)}`} />
                  <button type="submit">添加到此 NPC</button>
                </form>
              ) : (
                <small>选择 NPC 后添加</small>
              )}
              {!builtIn ? (
                <form className={styles.inlineAction} action={删除项目Skill.bind(null, projectId, skillId)}>
                  <input type="hidden" name="return_to" value={seedReturnPath} />
                  <button type="submit">删除</button>
                </form>
              ) : null}
            </article>
          )})}
          {resource.kind === "seat" ? (
            <article className={`${styles.editorCard} ${styles.wideCard}`}>
              <span>给这个 NPC 添加 Skill</span>
              <strong>用户手动创建 / 用户导入本地 Skill / 用户导入 GitHub 路径</strong>
              <div className={styles.actionColumns}>
                <form className={styles.stackForm} action={创建项目Skill.bind(null, projectId)}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                  <input type="hidden" name="assignment_seat_id" value={resource.seatRowId || resource.id} />
                  <input type="hidden" name="source" value="custom" />
                  {collaborationSeed ? (
                    <>
                      <input type="hidden" name="closure_source" value="company_collaboration" />
                      <input type="hidden" name="closure_need_id" value={text(collaborationSeed.rawNeedId, "")} />
                      <input type="hidden" name="closure_task_id" value={text(collaborationSeed.rawTaskId, "")} />
                      <input type="hidden" name="closure_dispatch_id" value={text(collaborationSeed.rawDispatchId, "")} />
                    </>
                  ) : null}
                  <label>Skill 标识<input name="skill_id" placeholder="my-debug-helper" /></label>
                  <label>显示名称<input name="label" placeholder="串口调试助手" defaultValue={collaborationSeed ? seedTitle : undefined} /></label>
                  <label>GitHub 仓库路径<input name="repo_relative_path" placeholder="skills/custom/my-debug-helper/SKILL.md" /></label>
                  <label>说明<textarea name="note" rows={3} placeholder="这个 Skill 让 NPC 学会什么、什么时候使用。" defaultValue={collaborationSeed ? seedSummary : undefined} /></label>
                  <button type="submit">用户手动创建并装配</button>
                </form>
                <form className={styles.stackForm} action={创建项目Skill.bind(null, projectId)}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                  <input type="hidden" name="assignment_seat_id" value={resource.seatRowId || resource.id} />
                  <input type="hidden" name="source" value="local-import" />
                  <label>本地 Skill 名称<input name="skill_id" placeholder="local-skill-name" /></label>
                  <label>显示名称<input name="label" placeholder="从本机导入的 Skill" /></label>
                  <label>同步后的 GitHub 路径<input name="repo_relative_path" placeholder="skills/imported/local-skill-name/SKILL.md" /></label>
                  <label>说明<textarea name="note" rows={3} placeholder="本地 Skill 必须同步到 GitHub 后才作为跨电脑事实源。" /></label>
                  <button type="submit">登记用户导入本地 Skill</button>
                </form>
                <form className={styles.stackForm} action={导入Github项目Skill.bind(null, projectId)}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                  <input type="hidden" name="assignment_seat_id" value={resource.seatRowId || resource.id} />
                  <input type="hidden" name="recommended_for" value={resource.id} />
                  <label>GitHub 地址<input name="github_url" placeholder="https://github.com/owner/repo/tree/main/skills" /></label>
                  <label>目录或文件路径<input name="github_path" placeholder="skills/my-skill/SKILL.md" /></label>
                  <label>分支<input name="github_branch" placeholder="main" /></label>
                  <button type="submit">从 GitHub 路径导入并装配</button>
                </form>
              </div>
              {availableSkills.length ? (
                <div className={styles.availableStrip}>
                  <span>仓库可添加</span>
                  {availableSkills.slice(0, 8).map((skill) => (
                    <form key={`add-${skillIdOf(skill)}`} className={styles.inlineAction} action={添加Skill到Npc.bind(null, projectId, resource.seatRowId || resource.id, skillIdOf(skill))}>
                      <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                      <button type="submit">{skillLabelOf(skill)}</button>
                    </form>
                  ))}
                </div>
              ) : null}
            </article>
          ) : null}
          {!skills.length ? (
            <article>
              <span>空仓库</span>
              <strong>还没有 Skill</strong>
              <p>主页面能力包仓库负责创建、导入和查看 Skill；这里负责把 Skill 配到工位或 NPC。</p>
            </article>
          ) : null}
        </section>
      ) : activeTab === "knowledge" ? (
        <section className={styles.skillGrid}>
          <article className={`${styles.editorCard} ${styles.knowledgeEditorCard}`}>
            <span>新增 / 编辑</span>
            <strong>{resource.name} 的知识条目</strong>
            <form className={`${styles.stackForm} ${styles.knowledgeForm}`} action={保存能力工坊知识库.bind(null, projectId)}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
              <input type="hidden" name="scope" value={resource.kind === "seat" ? "npc" : "workstation"} />
              <input type="hidden" name="owner_type" value={resource.kind === "seat" ? "seat" : "workstation"} />
              <input type="hidden" name="owner_id" value={resource.id} />
              {resource.kind === "seat" ? <input type="hidden" name="author_seat_id" value={resource.id} /> : null}
              {collaborationSeed ? (
                <>
                  <input type="hidden" name="closure_source" value="company_collaboration" />
                  <input type="hidden" name="closure_need_id" value={text(collaborationSeed.rawNeedId, "")} />
                  <input type="hidden" name="closure_task_id" value={text(collaborationSeed.rawTaskId, "")} />
                  <input type="hidden" name="closure_dispatch_id" value={text(collaborationSeed.rawDispatchId, "")} />
                </>
              ) : null}
              <label>
                标题
                <input name="title" placeholder={`${resource.name} 调试经验`} defaultValue={collaborationSeed ? seedTitle : undefined} />
              </label>
              <label>
                仓库相对路径
                <input name="repo_relative_path" placeholder={resource.kind === "seat" ? `${deposits?.knowledge ?? `docs/npc-knowledge/${resource.id}/`}notes.md` : workstationKnowledgePlaceholder(resource)} />
              </label>
              <label>
                摘要
                <textarea name="summary" rows={3} placeholder="这条知识解决什么问题、适合哪个 NPC 使用。" defaultValue={collaborationSeed ? seedSummary : undefined} />
              </label>
              <label>
                标签
                <input name="tags" placeholder="pid, foc, debug" />
              </label>
              <button type="submit">保存知识库</button>
            </form>
          </article>
          {(focusedKnowledge.length ? focusedKnowledge : documents.slice(0, 10)).map((doc, index) => (
            <article key={`doc-${docKeyOf(doc, index)}`}>
              <div className={styles.cardTopline}>
                <span>{docSourceLabel(doc)}</span>
                <small>{matchesKnowledge(doc, resource) || boundKnowledgePaths.has(docPathOf(doc)) ? "已绑定" : "可绑定"}</small>
              </div>
              <strong>{text(doc.title ?? doc.name ?? doc.path, `知识库 ${index + 1}`)}</strong>
              <p>{text(doc.summary ?? doc.description ?? docPathOf(doc), "等待补齐摘要、版本和审核状态。")}</p>
              <div className={styles.repoLine}>
                <b>仓库位置</b>
                {docPathOf(doc) ? <code>{docPathOf(doc)}</code> : <em>待补仓库路径</em>}
                {githubBlobHref(projectRepo, docPathOf(doc)) ? <a href={githubBlobHref(projectRepo, docPathOf(doc))} target="_blank" rel="noreferrer">打开 GitHub</a> : null}
              </div>
              <div className={styles.cardActions}>
                {matchesKnowledge(doc, resource) || boundKnowledgePaths.has(docPathOf(doc)) ? (
                  <small>已绑定</small>
                ) : resource.kind === "seat" ? (
                  <form className={styles.inlineAction} action={绑定知识库到Npc.bind(null, projectId, resource.seatRowId || resource.id, docKeyOf(doc, index))}>
                    <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?seat=${encodeURIComponent(resource.id)}`} />
                    <button type="submit">绑定到此 NPC</button>
                  </form>
                ) : (
                  <small>选择 NPC 后绑定</small>
                )}
                <form className={`${styles.inlineAction} ${styles.dangerAction}`} action={删除能力工坊知识库.bind(null, projectId, docKeyOf(doc, index))}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                  <button type="submit">删除索引</button>
                </form>
              </div>
            </article>
          ))}
          {!documents.length ? (
            <article>
              <span>空知识库</span>
              <strong>还没有知识库</strong>
              <p>先把项目、工位或 NPC 知识库导入仓库；这里会把真实知识库绑定到当前 NPC，并刷新上岗包摘要。</p>
            </article>
          ) : null}
          {deposits ? (
            <article className={`${styles.depositCard} ${styles.depositWideCard}`}>
              <span>NPC 默认写入路径</span>
              <strong>平台从这里索引知识和协作证据</strong>
              <ul>
                {[
                  ["知识", deposits.knowledge],
                  ["Skill", deposits.skill],
                  ["需求", deposits.need],
                  ["任务回执", deposits.task],
                ].map(([label, path]) => {
                  const href = githubRepoPathHref(projectRepo, path);
                  return (
                    <li key={label}>
                      <b>{label}</b>
                      <code>{path}</code>
                      {href ? <a href={href} target="_blank" rel="noreferrer">打开 GitHub</a> : null}
                    </li>
                  );
                })}
              </ul>
              <p>这些都是 GitHub 仓库相对路径；本地电脑只负责执行和同步。</p>
              <form className={styles.inlineAction} action={索引Npc沉淀.bind(null, projectId, resource.id)}>
                <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                <button type="submit">索引该 NPC 沉淀</button>
              </form>
            </article>
          ) : null}
        </section>
      ) : (
        <section className={`${styles.skillGrid} ${styles.gitGrid}`}>
          <article className={`${styles.gitCard} ${styles.gitSourceCard}`}>
            <span>GitHub 事实源</span>
            {githubRepoHref(projectRepo) ? (
              <strong><a href={githubRepoHref(projectRepo)} target="_blank" rel="noreferrer">{projectRepo}</a></strong>
            ) : (
              <strong>{projectRepo}</strong>
            )}
            <p>跨电脑协作只认 GitHub 仓库相对路径、提交、分支、PR 和平台证据；当前电脑工作副本只用于执行和同步提示。</p>
            <div className={styles.gitFlowChips} aria-label="Git 治理流程">
              <span>先预检</span>
              <span>收集证据</span>
              <span>公司层放行</span>
              <span>执行后回执</span>
            </div>
          </article>
          {gitMessages.map((message, index) => (
            <article key={text(message.id, `git-${index}`)} className={`${styles.gitCard} ${styles.gitEventCard}`}>
              <span>{messageTime(message) || "Git 记录"}</span>
              <strong>{userMessage(message.title, "Git 事件")}</strong>
              <p>{userMessage(message.body, "这条 Git 记录已归档到当前资源。").slice(0, 160)}</p>
              <small>{userMessage(message.status, "已记录")}</small>
            </article>
          ))}
          {!gitMessages.length ? (
            <article className={`${styles.gitCard} ${styles.gitEmptyCard}`}>
              <span>提交筛选</span>
              <strong>{resource.name} 还没有 Git 记录</strong>
              <p>只有该 NPC 发起、承接、审核、提交、预检或受影响的 Git 事件会落到这里；项目总池不会替代 NPC 自己的记录。</p>
            </article>
          ) : null}
          <article className={`${styles.gitCard} ${styles.gitSafetyCard}`}>
            <span>高风险边界</span>
            <strong>回退必须人审</strong>
            <p>回退只登记申请，不直接执行。平台会先收集目标版本、影响范围和证据，再交给公司层人工放行。</p>
          </article>
        </section>
      )}

      <section className={styles.materialRows}>
        <article>
          <div>
            <span>当前资源</span>
            <strong>{resourceLabel(resource)} / {resource.name}</strong>
            <p>这个瓷砖只展示该资源自己的 Skill、知识库和 Git 管理，不影响其他 NPC 的上岗包。</p>
          </div>
          <small>{tabLabel}</small>
        </article>
        <article className={styles.snapshotRow} data-state={runtimeSnapshots.length ? "ready" : "empty"}>
          <div>
            <span>上岗包</span>
            <strong>{runtimeSnapshots.length ? `${runtimeSnapshots[0].owner} · ${runtimeSnapshots[0].label}` : "配置源到运行快照"}</strong>
            <p>{runtimeSnapshots.length ? runtimeSnapshots[0].summary : "能力工坊保存配置源；NPC 工作台和执行电脑使用生成后的快照。"}</p>
            {runtimeSnapshots.length ? (
              <div className={styles.snapshotStack} aria-label="上岗包快照证据">
                {runtimeSnapshots.map((item) => (
                  <div key={item.id} className={styles.snapshotEvidence}>
                    <strong>{item.id === "knowledge" ? "知识库" : "Skill"} · {item.label}</strong>
                    <div className={styles.snapshotChips}>
                      <span>{item.generatedAt ? `刷新 ${item.generatedAt}` : "已生成快照"}</span>
                      <span>{item.effect}</span>
                      <span>{item.source}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <small>{runtimeSnapshots.length ? `${runtimeSnapshots.length} 条证据` : "待生成"}</small>
        </article>
        {deposits ? (
          <article>
            <div>
              <span>NPC 默认写入路径</span>
              <strong>知识 / Skill / 需求 / 任务回执</strong>
              <p>{deposits.knowledge} · {deposits.skill}</p>
            </div>
            <form className={styles.inlineAction} action={索引Npc沉淀.bind(null, projectId, resource.id)}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
              <button type="submit">索引该 NPC 沉淀</button>
            </form>
          </article>
        ) : null}
      </section>
    </article>
  );
}

export function SkillForgeClient({
  projectId,
  projectName,
  projectRepo,
  returnTo = "",
  returnToLabel = "",
  surfaceNotice = "",
  surfaceError = "",
  skills,
  documents,
  assignments,
  messages,
  seats,
  workstations,
  initialOpenResourceIds,
  initialActiveTab = "skills",
  initialCollaborationSeed = null,
}: SkillForgeClientProps) {
  const resources = useMemo(() => {
    const stationResources = workstations.map((station, index) => {
      const id = idOf(station) || `station-${index + 1}`;
      return { id, kind: "station" as const, name: nameOf(station, `工位 ${index + 1}`) };
    });
    const stationById = new Map(stationResources.map((station) => [station.id, station]));
    const seatResources = seats.map((seat, index) => {
      const id = idOf(seat) || `seat-${index + 1}`;
      const seatRowId = text(seat.row_id ?? seat.rowId ?? seat.id, id);
      const seatConfigId = text(seat.config_id ?? seat.configId, id);
      const parentId = seatParentId(seat);
      const parent = parentId ? stationById.get(parentId) : null;
      return {
        id,
        kind: "seat" as const,
        name: nameOf(seat, `NPC ${index + 1}`),
        seatRowId,
        seatConfigId,
        parentId,
        parentName: parent?.name || "未归属工位",
      };
    });
    return [...stationResources, ...seatResources];
  }, [seats, workstations]);
  const knownResourceKeys = new Set(resources.map(resourceKey));
  const seededOpenIds = uniqueIds(initialOpenResourceIds.filter((id) => knownResourceKeys.has(id)));
  const [openIds, setOpenIds] = useState<string[]>(seededOpenIds);
  const openResources = uniqueIds(openIds).map((id) => resources.find((resource) => resourceKey(resource) === id)).filter(Boolean) as ForgeResource[];
  const draftSkills = skills.filter((item) => /draft|pending|review/i.test(text(item.draft_status ?? item.draftStatus ?? item.status, "")));
  const npcAuthored = skills.filter((item) => /npc|agent/i.test(text(item.source ?? item.created_by_type ?? item.author_type, "")));
  const receiptMessage = userMessage(surfaceError || surfaceNotice, "");
  const receiptState = surfaceError ? "error" : surfaceNotice ? "success" : "";
  const workspaceRef = useRef<HTMLElement | null>(null);

  function focusWorkspaceOnMobile() {
    if (typeof window === "undefined" || !window.matchMedia("(max-width: 760px)").matches) return;
    window.setTimeout(() => {
      workspaceRef.current?.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
    }, 80);
  }

  useEffect(() => {
    if (seededOpenIds.length <= 0) return;
    if (typeof window === "undefined" || !window.matchMedia("(max-width: 760px)").matches) return;
    window.setTimeout(() => {
      workspaceRef.current?.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
    }, 120);
  }, [seededOpenIds.length]);

  function toggleResource(id: string) {
    setOpenIds((curr) => {
      if (curr.includes(id)) return curr.filter((item) => item !== id);
      focusWorkspaceOnMobile();
      return uniqueIds([...curr, id]);
    });
  }

  function openRecommendedResources() {
    setOpenIds(resources.slice(0, 2).map(resourceKey));
    focusWorkspaceOnMobile();
  }

  function openAllResources() {
    setOpenIds(resources.map(resourceKey));
    focusWorkspaceOnMobile();
  }

  function closeResource(id: string) {
    setOpenIds((curr) => curr.filter((item) => item !== id));
  }

  return (
    <main className={`${workbenchStyles.shell} ${styles.forgeShell}`}>
      <header className={`${workbenchStyles.topbar} ${styles.forgeTopbar}`}>
        <div className={workbenchStyles.topbarLeft}>
          <Link href={`/projects/${projectId}/2d-upgrade`} className={`${workbenchStyles.backLink} ${styles.forgeBackLink}`}>← 主页面</Link>
          {returnTo ? <Link href={returnTo} className={`${workbenchStyles.backLink} ${styles.forgeBackLink}`}>{returnToLabel || "← 返回来源"}</Link> : null}
          <div className={`${workbenchStyles.title} ${styles.forgeTitle}`}>
            <strong>{projectName}</strong>
            <small>能力工坊 · Skill、知识库、Git 治理资产统一整理</small>
          </div>
        </div>
        <div className={workbenchStyles.topbarRight}>
          {surfaceError ? <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>需要处理</span> : null}
          {surfaceNotice ? <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>已记录</span> : null}
          <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>Skill {skills.length}</span>
          <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>草稿 {draftSkills.length}</span>
          <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>自定义绑定 {assignments.length}</span>
          <span className={`${workbenchStyles.kpi} ${styles.forgeKpi}`}>已打开 {openResources.length}</span>
        </div>
      </header>

      <div className={`${workbenchStyles.body} ${styles.forgeBody}`}>
        <aside className={`${workbenchStyles.sidebar} ${styles.forgeSidebar}`}>
          <div className={`${workbenchStyles.sidebarHeader} ${styles.forgeSidebarHeader}`}>
            <input
              type="search"
              className={`${workbenchStyles.search} ${styles.forgeSearch}`}
              placeholder="搜索工位 / NPC / Skill"
              readOnly
              value="资源索引：工位 / NPC / 能力"
            />
            <div className={styles.forgeQuickActions}>
              <button type="button" className={`${workbenchStyles.batchBtn} ${styles.forgeBatchBtn}`} onClick={openRecommendedResources}>
                打开推荐 ({Math.min(resources.length, 2)})
              </button>
              <button type="button" className={`${workbenchStyles.batchBtn} ${styles.forgeBatchBtn} ${styles.forgeBatchBtnGhost}`} onClick={openAllResources}>
                全部 ({resources.length})
              </button>
            </div>
            <div className={styles.forgeScrollHint} aria-hidden="true">继续下滑查看更多 NPC</div>
          </div>
          <ul className={`${workbenchStyles.groupList} ${styles.forgeGroupList}`} aria-label="工位和 NPC 索引">
            {workstations.map((station, stationIndex) => {
              const stationId = idOf(station) || `station-${stationIndex + 1}`;
              const stationKey = `station:${stationId}`;
              const stationSeats = resources.filter((resource) => resource.kind === "seat" && resource.parentId === stationId) as ForgeResource[];
              return (
                <li key={stationKey} className={`${workbenchStyles.group} ${styles.forgeGroup}`}>
                  <div className={`${workbenchStyles.groupHeader} ${styles.forgeGroupHeader}`}>
                    <span>🏷 {nameOf(station, `工位 ${stationIndex + 1}`)}</span>
                    <small>{stationSeats.length} 个 NPC</small>
                  </div>
                  <ul className={`${workbenchStyles.npcList} ${styles.forgeNpcList}`}>
                    <li className={`${workbenchStyles.npcRow} ${styles.forgeNpcRow} ${openIds.includes(stationKey) ? `${workbenchStyles.npcRowOpen} ${styles.forgeNpcRowOpen}` : ""}`}>
                      <div className={workbenchStyles.npcMain}>
                        <strong className={`${workbenchStyles.npcName} ${styles.forgeNpcName}`}>{nameOf(station, `工位 ${stationIndex + 1}`)}</strong>
                        <small className={`${workbenchStyles.npcMeta} ${styles.forgeNpcMeta}`}>
                          <span className={`${workbenchStyles.dot} ${styles.forgeDot}`} />
                          工位配置 · Skill / 知识库 / Git
                        </small>
                      </div>
                      <button
                        type="button"
                        className={`${workbenchStyles.openBtn} ${styles.forgeOpenBtn}`}
                        onClick={() => toggleResource(stationKey)}
                        title={openIds.includes(stationKey) ? "关闭瓷砖" : "打开瓷砖"}
                        aria-label={`${openIds.includes(stationKey) ? "关闭" : "打开"} ${nameOf(station, `工位 ${stationIndex + 1}`)} 配置瓷砖`}
                      >
                        {openIds.includes(stationKey) ? "✕" : "+"}
                      </button>
                    </li>
                    {stationSeats.map((seat) => {
                      const key = resourceKey(seat);
                      const parentName = seat.kind === "seat" ? seat.parentName : "";
                      return (
                        <li key={key} className={`${workbenchStyles.npcRow} ${styles.forgeNpcRow} ${openIds.includes(key) ? `${workbenchStyles.npcRowOpen} ${styles.forgeNpcRowOpen}` : ""}`}>
                          <div className={workbenchStyles.npcMain}>
                            <strong className={`${workbenchStyles.npcName} ${styles.forgeNpcName}`}>{seat.name}</strong>
                            <small className={`${workbenchStyles.npcMeta} ${styles.forgeNpcMeta}`}>
                              <span className={`${workbenchStyles.dot} ${styles.forgeDot}`} />
                              NPC 配置 · {parentName || "未归属工位"}
                            </small>
                          </div>
                          <button
                            type="button"
                            className={`${workbenchStyles.openBtn} ${styles.forgeOpenBtn}`}
                            onClick={() => toggleResource(key)}
                            title={openIds.includes(key) ? "关闭瓷砖" : "打开瓷砖"}
                            aria-label={`${openIds.includes(key) ? "关闭" : "打开"} ${seat.name} 配置瓷砖`}
                          >
                            {openIds.includes(key) ? "✕" : "+"}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
            {resources.some((resource) => resource.kind === "seat" && !resource.parentId) ? (
              <li className={`${workbenchStyles.group} ${styles.forgeGroup}`}>
                <div className={`${workbenchStyles.groupHeader} ${styles.forgeGroupHeader}`}>
                  <span>未归属 NPC</span>
                  <small>{resources.filter((resource) => resource.kind === "seat" && !resource.parentId).length} 个 NPC</small>
                </div>
                <ul className={`${workbenchStyles.npcList} ${styles.forgeNpcList}`}>
                  {resources.filter((resource) => resource.kind === "seat" && !resource.parentId).map((seat) => {
                    const key = resourceKey(seat);
                    return (
                      <li key={key} className={`${workbenchStyles.npcRow} ${styles.forgeNpcRow} ${openIds.includes(key) ? `${workbenchStyles.npcRowOpen} ${styles.forgeNpcRowOpen}` : ""}`}>
                        <div className={workbenchStyles.npcMain}>
                          <strong className={`${workbenchStyles.npcName} ${styles.forgeNpcName}`}>{seat.name}</strong>
                          <small className={`${workbenchStyles.npcMeta} ${styles.forgeNpcMeta}`}>
                            <span className={`${workbenchStyles.dot} ${styles.forgeDot}`} />
                            NPC 配置 · 待分配工位
                          </small>
                        </div>
                        <button
                          type="button"
                          className={`${workbenchStyles.openBtn} ${styles.forgeOpenBtn}`}
                          onClick={() => toggleResource(key)}
                          title={openIds.includes(key) ? "关闭瓷砖" : "打开瓷砖"}
                          aria-label={`${openIds.includes(key) ? "关闭" : "打开"} ${seat.name} 配置瓷砖`}
                        >
                          {openIds.includes(key) ? "✕" : "+"}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ) : null}
            {!workstations.length ? (
              <li className={`${workbenchStyles.group} ${styles.forgeGroup}`}>
                <div className={`${workbenchStyles.groupHeader} ${styles.forgeGroupHeader}`}>
                  <span>还没有工位</span>
                  <small>先创建工位和 NPC</small>
                </div>
              </li>
            ) : null}
          </ul>
        </aside>

        <section ref={workspaceRef} className={`${workbenchStyles.main} ${styles.forgeMain}`} data-mode={openResources.length > 0 ? "chat" : "setup"} data-has-receipt={receiptMessage ? "1" : "0"}>
          {receiptMessage ? (
            <section className={styles.forgeReceipt} data-state={receiptState} role="status" aria-live="polite">
              <div>
                <span>{surfaceError ? "操作需要处理" : "操作回执"}</span>
                <strong>{receiptMessage}</strong>
                <p>{surfaceError ? "请按提示补齐信息后重试；平台不会把未完成配置写进 NPC 的运行上下文。" : "配置源已更新，刷新后的上岗包和下一轮派单会读取这份配置；正在执行的任务仍保持原快照。"}</p>
              </div>
              <div className={styles.receiptActions}>
                {!openResources.length ? <button type="button" onClick={openRecommendedResources}>打开推荐资源</button> : null}
                {returnTo ? <Link href={returnTo}>{returnToLabel || "返回来源"}</Link> : null}
              </div>
            </section>
          ) : null}
          {openResources.length ? (
            <div className={`${workbenchStyles.tileGrid} ${styles.forgeTileGrid}`} data-tile-count={openResources.length}>
              {openResources.map((resource) => {
                const key = resourceKey(resource);
                return (
                  <ForgeTile
                    key={key}
                    projectId={projectId}
                    projectRepo={projectRepo}
                    resource={resource}
                    sourceSeat={resource.kind === "seat" ? seats.find((seat) => seatMatchesResource(seat, resource)) ?? null : null}
                    openIds={openIds}
                    skills={skills}
                    documents={documents}
                    assignments={assignments}
                    messages={messages}
                    seats={seats}
                    initialActiveTab={initialActiveTab}
                    collaborationSeed={initialCollaborationSeed}
                    onClose={() => closeResource(key)}
                  />
                );
              })}
            </div>
          ) : (
            <div className={`${workbenchStyles.placeholder} ${styles.forgePlaceholder}`}>
              <strong>先从左侧选择一个工位或 NPC</strong>
              <p>打开后只看该对象自己的 Skill、知识库和 Git 治理证据；不会把全部功能一次性堆出来。</p>
              <div className={styles.placeholderActions}>
                <button type="button" onClick={openRecommendedResources}>打开推荐资源</button>
                <span>或点击左侧任意 “+” 打开单个资源瓷砖</span>
              </div>
              <div className={styles.placeholderSteps} aria-label="能力工坊使用步骤">
                <span>选资源</span>
                <span>看 Skill / 知识库 / Git</span>
                <span>保存后进入下一轮上岗包</span>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
