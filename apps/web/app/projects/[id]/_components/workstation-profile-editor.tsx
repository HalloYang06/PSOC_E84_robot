"use client";

import { useEffect, useState } from "react";
import styles from "./workstation-profile-editor.module.css";
import { apiClientUrl } from "../../../../lib/api-client-url";

type Props = {
  apiBaseUrl: string;
  projectId: string;
  nodeId: string;
};

export function WorkstationProfileEditor({ apiBaseUrl, projectId, nodeId }: Props) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [localPath, setLocalPath] = useState("");
  const [reviewPolicy, setReviewPolicy] = useState("inherit");
  const [knowledgePath, setKnowledgePath] = useState(`docs/workstations/${nodeId}.md`);
  const [skillInheritance, setSkillInheritance] = useState("");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open || loaded) return;
    (async () => {
      try {
        const res = await fetch(
          apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/config`),
          { credentials: "include" },
        );
        const json = await res.json().catch(() => ({}));
        const inner =
          json?.data?.collaboration_config ?? json?.collaboration_config ?? json?.data ?? json;
        const profiles = (inner?.workstation_profiles || {}) as Record<string, any>;
        const cur = profiles[nodeId] || {};
        if (cur.local_repo_path) setLocalPath(String(cur.local_repo_path));
        if (cur.review_policy) setReviewPolicy(String(cur.review_policy));
        if (cur.knowledge_path) setKnowledgePath(String(cur.knowledge_path));
        if (Array.isArray(cur.skill_inheritance)) {
          setSkillInheritance(cur.skill_inheritance.join(", "));
        }
      } catch {
        /* ignore — UI 会用默认值 */
      } finally {
        setLoaded(true);
      }
    })();
  }, [open, loaded, apiBaseUrl, projectId, nodeId]);

  async function save() {
    setSaving(true);
    setNote(null);
    try {
      const res = await fetch(
        apiClientUrl(`/api/collaboration/projects/${encodeURIComponent(projectId)}/workstation-profiles/${encodeURIComponent(nodeId)}`),
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            local_repo_path: localPath.trim() || null,
            review_policy: reviewPolicy,
            knowledge_path: knowledgePath.trim() || null,
            skill_inheritance: skillInheritance
              .split(/[,\n]+/)
              .map((s) => s.trim())
              .filter(Boolean),
          }),
        },
      );
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = json?.error?.message ?? json?.message ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setNote("已保存 ✓（刷新可见同步）");
    } catch (e) {
      setNote(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSaving(false);
      setTimeout(() => setNote(null), 4000);
    }
  }

  if (!open) {
    return (
      <button type="button" className={styles.toggle} onClick={() => setOpen(true)}>
        ⚙ 工位设置（路径 / 审核 / 知识库）
      </button>
    );
  }

  return (
    <div className={styles.box}>
      <div className={styles.row}>
        <label className={styles.label}>本地仓库路径（本机）</label>
        <input
          className={styles.input}
          value={localPath}
          onChange={(e) => setLocalPath(e.target.value)}
          placeholder="例如：D:\\ai合作产品 或 /home/x/repo"
        />
      </div>
      <div className={styles.row}>
        <label className={styles.label}>工位审核策略</label>
        <select
          className={styles.input}
          value={reviewPolicy}
          onChange={(e) => setReviewPolicy(e.target.value)}
        >
          <option value="inherit">继承项目（默认）</option>
          <option value="force">强制人审</option>
          <option value="skip">免审（信任本工位）</option>
        </select>
      </div>
      <div className={styles.row}>
        <label className={styles.label}>工位知识库路径</label>
        <input
          className={styles.input}
          value={knowledgePath}
          onChange={(e) => setKnowledgePath(e.target.value)}
          placeholder="docs/workstations/<id>.md"
        />
      </div>
      <div className={styles.row}>
        <label className={styles.label}>工位继承的 skill（逗号分隔，本工位 NPC 默认带上）</label>
        <input
          className={styles.input}
          value={skillInheritance}
          onChange={(e) => setSkillInheritance(e.target.value)}
          placeholder="例如：claude-code-skill, mcp-fs, scorecard-poll"
        />
      </div>
      <div className={styles.actions}>
        <button type="button" className={styles.saveBtn} onClick={save} disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </button>
        <button type="button" className={styles.cancelBtn} onClick={() => setOpen(false)}>
          收起
        </button>
        {note ? <small className={styles.note}>{note}</small> : null}
      </div>
    </div>
  );
}
