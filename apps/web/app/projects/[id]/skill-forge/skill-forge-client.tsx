"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { 删除能力工坊知识库, 删除项目Skill, 保存能力工坊知识库, 添加Skill到Npc, 索引Npc沉淀, 绑定知识库到Npc } from "../../../actions";
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
  return next
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

function skillIdOf(value: AnyRecord) {
  return text(value.skill_id ?? value.skillId ?? value.id ?? value.slug, "").toLowerCase();
}

function skillLabelOf(value: AnyRecord, fallback = "Skill") {
  return text(value.label ?? value.name ?? value.title ?? value.skill_id ?? value.id, fallback);
}

function skillDescriptionOf(value: AnyRecord) {
  return text(value.description ?? value.note ?? value.summary, "");
}

function skillSourceLabel(value: AnyRecord) {
  const source = text(value.source ?? value.category, "项目 Skill");
  if (/npc|agent/i.test(source)) return "NPC 沉淀";
  if (/human|custom/i.test(source)) return "用户添加";
  if (/github|repo/i.test(source)) return "GitHub 导入";
  return source;
}

function isBuiltInSkill(value: AnyRecord) {
  const source = text(value.source, "").toLowerCase();
  const scope = text(value.scope, "").toLowerCase();
  return source.startsWith("platform-") || scope === "baseline" || value.required === true;
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
  if (/npc|agent/i.test(source)) return "NPC 沉淀";
  if (/human|custom/i.test(source)) return "用户添加";
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
}) {
  const [activeTab, setActiveTab] = useState<ForgeTab>("skills");
  const focusedAssignments = assignments.filter((assignment) => matchesAssignment(assignment, resource));
  const boundKnowledgePaths = new Set(resource.kind === "seat" && sourceSeat ? knowledgePathsOf(sourceSeat) : []);
  const focusedKnowledge = documents.filter((doc) => matchesKnowledge(doc, resource) || boundKnowledgePaths.has(docPathOf(doc)));
  const assignedSkillIds = new Set([
    ...focusedAssignments.map(skillIdOf),
    ...(resource.kind === "seat" && sourceSeat ? roleSkillLoadoutOf(sourceSeat) : []),
  ].filter(Boolean));
  const orderedSkills = [...skills].sort((left, right) => {
    const leftBuiltIn = isBuiltInSkill(left) ? 1 : 0;
    const rightBuiltIn = isBuiltInSkill(right) ? 1 : 0;
    if (leftBuiltIn !== rightBuiltIn) return leftBuiltIn - rightBuiltIn;
    const leftAssigned = assignedSkillIds.has(skillIdOf(left)) ? 0 : 1;
    const rightAssigned = assignedSkillIds.has(skillIdOf(right)) ? 0 : 1;
    if (leftAssigned !== rightAssigned) return leftAssigned - rightAssigned;
    return skillLabelOf(left).localeCompare(skillLabelOf(right), "zh-Hans-CN");
  });
  const snapshot = sourceSeat?.metadata?.skill_forge_snapshot ?? sourceSeat?.extra_data?.skill_forge_snapshot ?? null;
  const deposits = resource.kind === "seat" ? npcDepositPaths(sourceSeat, resource) : null;
  const tabLabel = activeTab === "knowledge" ? "知识库配置" : activeTab === "git" ? "Git 管理" : "Skill 配置";
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
          ["skills", "Skill 配置", focusedAssignments.length],
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

      {activeTab === "skills" ? (
        <section className={styles.skillGrid}>
          {resource.kind === "seat" ? (
            <article className={styles.editorCard}>
              <span>仓库闭环</span>
              <strong>Skill 从工作中沉淀</strong>
              <p>NPC 工作中形成的可复用 Skill 先写入自己的仓库目录，再由平台索引进仓库；用户仍可编辑、删除和分配。</p>
              {deposits ? <small>{deposits.skill}</small> : null}
            </article>
          ) : null}
          {orderedSkills.slice(0, 10).map((skill, index) => (
            <article key={text(skill.id ?? skill.name, `skill-${index}`)}>
              <span>{skillSourceLabel(skill)}</span>
              <strong>{skillLabelOf(skill, `Skill ${index + 1}`)}</strong>
              <p>{skillDescriptionOf(skill) || "暂无说明"}</p>
              {isBuiltInSkill(skill) ? (
                <small>固定必备</small>
              ) : assignedSkillIds.has(skillIdOf(skill)) ? (
                <small>已关联</small>
              ) : resource.kind === "seat" ? (
                <form className={styles.inlineAction} action={添加Skill到Npc.bind(null, projectId, resource.seatRowId || resource.id, skillIdOf(skill))}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?seat=${encodeURIComponent(resource.id)}`} />
                  <button type="submit">添加到此 NPC</button>
                </form>
              ) : (
                <small>选择 NPC 后添加</small>
              )}
              {!isBuiltInSkill(skill) ? (
                <form className={styles.inlineAction} action={删除项目Skill.bind(null, projectId, skillIdOf(skill))}>
                  <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                  <button type="submit">删除</button>
                </form>
              ) : null}
            </article>
          ))}
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
          <article className={styles.editorCard}>
            <span>新增 / 编辑</span>
            <strong>{resource.name} 的知识条目</strong>
            <form className={styles.stackForm} action={保存能力工坊知识库.bind(null, projectId)}>
              <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
              <input type="hidden" name="scope" value={resource.kind === "seat" ? "npc" : "workstation"} />
              <input type="hidden" name="owner_type" value={resource.kind === "seat" ? "seat" : "workstation"} />
              <input type="hidden" name="owner_id" value={resource.id} />
              {resource.kind === "seat" ? <input type="hidden" name="author_seat_id" value={resource.id} /> : null}
              <label>
                标题
                <input name="title" placeholder={`${resource.name} 调试经验`} />
              </label>
              <label>
                仓库相对路径
                <input name="repo_relative_path" placeholder={resource.kind === "seat" ? `${deposits?.knowledge ?? `docs/npc-knowledge/${resource.id}/`}notes.md` : workstationKnowledgePlaceholder(resource)} />
              </label>
              <label>
                摘要
                <textarea name="summary" rows={3} placeholder="这条知识解决什么问题、适合哪个 NPC 使用。" />
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
              <span>{docSourceLabel(doc)}</span>
              <strong>{text(doc.title ?? doc.name ?? doc.path, `知识库 ${index + 1}`)}</strong>
              <p>{text(doc.summary ?? doc.description ?? docPathOf(doc), "等待补齐摘要、版本和审核状态。")}</p>
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
              <form className={styles.inlineAction} action={删除能力工坊知识库.bind(null, projectId, docKeyOf(doc, index))}>
                <input type="hidden" name="return_to" value={`/projects/${projectId}/skill-forge?resources=${encodeURIComponent(resourceKey(resource))}`} />
                <button type="submit">删除</button>
              </form>
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
            <article className={styles.depositCard}>
              <span>NPC 默认写入路径</span>
              <strong>平台从这里索引知识和协作证据</strong>
              <ul>
                <li><b>知识</b><code>{deposits.knowledge}</code></li>
                <li><b>Skill</b><code>{deposits.skill}</code></li>
                <li><b>需求</b><code>{deposits.need}</code></li>
                <li><b>任务回执</b><code>{deposits.task}</code></li>
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
        <section className={styles.skillGrid}>
          <article>
            <span>GitHub 事实源</span>
            <strong>{projectRepo}</strong>
            <p>跨电脑协作只认 GitHub 仓库相对路径、提交、分支、PR 和平台证据；本地目录只是当前电脑工作副本。</p>
          </article>
          {gitMessages.map((message, index) => (
            <article key={text(message.id, `git-${index}`)}>
              <span>{messageTime(message) || "Git 记录"}</span>
              <strong>{text(message.title, "Git 事件")}</strong>
              <p>{text(message.body, "这条 Git 记录已归档到当前资源。").slice(0, 160)}</p>
              <small>{text(message.status, "已记录")}</small>
            </article>
          ))}
          {!gitMessages.length ? (
            <article>
              <span>提交筛选</span>
              <strong>{resource.name} 还没有 Git 记录</strong>
              <p>只有该 NPC 发起、承接、审核、提交、预检或受影响的 Git 事件会落到这里；项目总池不会替代 NPC 自己的记录。</p>
            </article>
          ) : null}
          <article>
            <span>高风险边界</span>
            <strong>回退必须人审</strong>
            <p>NPC 可以提交建议和预演，平台先登记请求、收集证据，再由用户放行。</p>
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
        <article>
          <div>
            <span>上岗包</span>
            <strong>{snapshot ? text(snapshot.changed_skill_label, "配置已更新") : "配置源到运行快照"}</strong>
            <p>{snapshot ? text(snapshot.summary, "能力配置已同步到该 NPC。") : "能力工坊保存配置源；NPC 工作台和执行电脑使用生成后的快照。"}</p>
          </div>
          <small>{snapshot ? "已刷新" : "待生成"}</small>
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
  const [openIds, setOpenIds] = useState<string[]>(seededOpenIds.length ? seededOpenIds : resources.slice(0, Math.min(2, resources.length)).map(resourceKey));
  const openResources = uniqueIds(openIds).map((id) => resources.find((resource) => resourceKey(resource) === id)).filter(Boolean) as ForgeResource[];
  const draftSkills = skills.filter((item) => /draft|pending|review/i.test(text(item.draft_status ?? item.draftStatus ?? item.status, "")));
  const npcAuthored = skills.filter((item) => /npc|agent/i.test(text(item.source ?? item.created_by_type ?? item.author_type, "")));

  function toggleResource(id: string) {
    setOpenIds((curr) => curr.includes(id) ? curr.filter((item) => item !== id) : uniqueIds([...curr, id]));
  }

  function closeResource(id: string) {
    setOpenIds((curr) => curr.filter((item) => item !== id));
  }

  return (
    <main className={workbenchStyles.shell}>
      <header className={workbenchStyles.topbar}>
        <div className={workbenchStyles.topbarLeft}>
          <Link href={`/projects/${projectId}/2d-upgrade`} className={workbenchStyles.backLink}>← 主页面</Link>
          {returnTo ? <Link href={returnTo} className={workbenchStyles.backLink}>{returnToLabel || "← 返回来源"}</Link> : null}
          <div className={workbenchStyles.title}>
            <strong>{projectName}</strong>
            <small>能力工坊 · 工位 / NPC 独立配置瓷砖</small>
          </div>
        </div>
        <div className={workbenchStyles.topbarRight}>
          {surfaceError ? <span className={workbenchStyles.kpi}>需要处理：{userMessage(surfaceError)}</span> : null}
          {surfaceNotice ? <span className={workbenchStyles.kpi}>{userMessage(surfaceNotice)}</span> : null}
          <span className={workbenchStyles.kpi}>Skill {skills.length}</span>
          <span className={workbenchStyles.kpi}>草稿 {draftSkills.length}</span>
          <span className={workbenchStyles.kpi}>绑定 {assignments.length}</span>
          <span className={workbenchStyles.kpi}>已打开 {openResources.length}</span>
        </div>
      </header>

      <div className={workbenchStyles.body}>
        <aside className={workbenchStyles.sidebar}>
          <div className={workbenchStyles.sidebarHeader}>
            <input
              type="search"
              className={workbenchStyles.search}
              placeholder="搜索工位 / NPC / Skill"
              readOnly
              value="能力工坊"
            />
            <button type="button" className={workbenchStyles.batchBtn} onClick={() => setOpenIds(resources.map(resourceKey))}>
              打开全部 ({resources.length})
            </button>
          </div>
          <ul className={workbenchStyles.groupList} aria-label="工位和 NPC 索引">
            {workstations.map((station, stationIndex) => {
              const stationId = idOf(station) || `station-${stationIndex + 1}`;
              const stationKey = `station:${stationId}`;
              const stationSeats = resources.filter((resource) => resource.kind === "seat" && resource.parentId === stationId) as ForgeResource[];
              return (
                <li key={stationKey} className={workbenchStyles.group}>
                  <div className={workbenchStyles.groupHeader}>
                    <span>🏷 {nameOf(station, `工位 ${stationIndex + 1}`)}</span>
                    <small>{stationSeats.length} 个 NPC</small>
                  </div>
                  <ul className={workbenchStyles.npcList}>
                    <li className={`${workbenchStyles.npcRow} ${openIds.includes(stationKey) ? workbenchStyles.npcRowOpen : ""}`}>
                      <div className={workbenchStyles.npcMain}>
                        <strong className={workbenchStyles.npcName}>{nameOf(station, `工位 ${stationIndex + 1}`)}</strong>
                        <small className={workbenchStyles.npcMeta}>
                          <span className={workbenchStyles.dot} />
                          工位配置 · Skill / 知识库 / Git
                        </small>
                      </div>
                      <a
                        className={workbenchStyles.openBtn}
                        href={forgeHref(projectId, openIds.includes(stationKey) ? openIds.filter((id) => id !== stationKey) : [...openIds, stationKey])}
                        onClick={(event) => {
                          event.preventDefault();
                          toggleResource(stationKey);
                        }}
                        title={openIds.includes(stationKey) ? "关闭瓷砖" : "打开瓷砖"}
                      >
                        {openIds.includes(stationKey) ? "✕" : "+"}
                      </a>
                    </li>
                    {stationSeats.map((seat) => {
                      const key = resourceKey(seat);
                      const parentName = seat.kind === "seat" ? seat.parentName : "";
                      return (
                        <li key={key} className={`${workbenchStyles.npcRow} ${openIds.includes(key) ? workbenchStyles.npcRowOpen : ""}`}>
                          <div className={workbenchStyles.npcMain}>
                            <strong className={workbenchStyles.npcName}>{seat.name}</strong>
                            <small className={workbenchStyles.npcMeta}>
                              <span className={workbenchStyles.dot} />
                              NPC 配置 · {parentName || "未归属工位"}
                            </small>
                          </div>
                          <a
                            className={workbenchStyles.openBtn}
                            href={forgeHref(projectId, openIds.includes(key) ? openIds.filter((id) => id !== key) : [...openIds, key])}
                            onClick={(event) => {
                              event.preventDefault();
                              toggleResource(key);
                            }}
                            title={openIds.includes(key) ? "关闭瓷砖" : "打开瓷砖"}
                          >
                            {openIds.includes(key) ? "✕" : "+"}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
            {resources.some((resource) => resource.kind === "seat" && !resource.parentId) ? (
              <li className={workbenchStyles.group}>
                <div className={workbenchStyles.groupHeader}>
                  <span>未归属 NPC</span>
                  <small>{resources.filter((resource) => resource.kind === "seat" && !resource.parentId).length} 个 NPC</small>
                </div>
                <ul className={workbenchStyles.npcList}>
                  {resources.filter((resource) => resource.kind === "seat" && !resource.parentId).map((seat) => {
                    const key = resourceKey(seat);
                    return (
                      <li key={key} className={`${workbenchStyles.npcRow} ${openIds.includes(key) ? workbenchStyles.npcRowOpen : ""}`}>
                        <div className={workbenchStyles.npcMain}>
                          <strong className={workbenchStyles.npcName}>{seat.name}</strong>
                          <small className={workbenchStyles.npcMeta}>
                            <span className={workbenchStyles.dot} />
                            NPC 配置 · 待分配工位
                          </small>
                        </div>
                        <a
                          className={workbenchStyles.openBtn}
                          href={forgeHref(projectId, openIds.includes(key) ? openIds.filter((id) => id !== key) : [...openIds, key])}
                          onClick={(event) => {
                            event.preventDefault();
                            toggleResource(key);
                          }}
                          title={openIds.includes(key) ? "关闭瓷砖" : "打开瓷砖"}
                        >
                          {openIds.includes(key) ? "✕" : "+"}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ) : null}
            {!workstations.length ? (
              <li className={workbenchStyles.group}>
                <div className={workbenchStyles.groupHeader}>
                  <span>还没有工位</span>
                  <small>先创建工位和 NPC</small>
                </div>
              </li>
            ) : null}
          </ul>
        </aside>

        <section className={workbenchStyles.main} data-mode={openResources.length > 0 ? "chat" : "setup"}>
          {openResources.length ? (
            <div className={workbenchStyles.tileGrid} data-tile-count={openResources.length}>
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
                    onClose={() => closeResource(key)}
                  />
                );
              })}
            </div>
          ) : (
            <div className={workbenchStyles.placeholder}>
              <strong>点击左栏工位或 NPC 的 + 号打开配置瓷砖</strong>
              <p>每个瓷砖都有自己的 Skill 配置、知识库配置和 Git 管理。</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
