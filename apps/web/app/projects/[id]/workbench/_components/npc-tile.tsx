"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./npc-tile.module.css";

export type WorkbenchSeat = {
  id: string;
  name: string;
  computerNodeId: string;
  computerNodeName: string;
  providerId: string;
  providerLabel: string;
  responsibility: string;
  skillLoadout: string[];
  knowledgeSummary: string;
  automationEnabled: boolean;
  model: string;
  permissionLevel: string;
};

type NpcTileProps = {
  projectId: string;
  seat: WorkbenchSeat;
  onClose: () => void;
};

export function NpcTile({ projectId, seat, onClose }: NpcTileProps) {
  const [showFullKnowledge, setShowFullKnowledge] = useState(false);

  const knowledgePreview =
    seat.knowledgeSummary.length > 80 ? `${seat.knowledgeSummary.slice(0, 80)}…` : seat.knowledgeSummary;
  const skillVisible = seat.skillLoadout.slice(0, 4);
  const skillExtra = seat.skillLoadout.length - skillVisible.length;

  return (
    <article className={styles.tile}>
      <header className={styles.head}>
        <div className={styles.headLeft}>
          <strong className={styles.name} title={seat.name}>
            {seat.name}
          </strong>
          <small className={styles.subline}>
            <span title="所属电脑">🖥 {seat.computerNodeName || "未绑定"}</span>
            <span title="模型 provider">⚙ {seat.providerLabel || seat.providerId || "未绑定"}</span>
            {seat.model ? <span title="模型">· {seat.model}</span> : null}
          </small>
        </div>
        <button type="button" className={styles.closeBtn} onClick={onClose} title="关闭这个瓷砖">
          ✕
        </button>
      </header>

      <div className={styles.metrics}>
        <div className={styles.metric} title="本周 token 消耗（per-NPC 数据待 S6 后端补）">
          <span className={styles.metricLabel}>7d Token</span>
          <span className={styles.metricValueMuted}>统计中</span>
        </div>
        <div className={styles.metric} title="上下文健康度（待 S6）">
          <span className={styles.metricLabel}>上下文</span>
          <span className={styles.metricValueMuted}>待统计</span>
        </div>
        <div className={styles.metric} title="自动化状态">
          <span className={styles.metricLabel}>自动化</span>
          <span className={seat.automationEnabled ? styles.metricValueOk : styles.metricValueMuted}>
            {seat.automationEnabled ? "已开" : "未开"}
          </span>
        </div>
        <div className={styles.metric} title="占用状态（S5 接入后实时刷新）">
          <span className={styles.metricLabel}>占用</span>
          <span className={styles.metricValueMuted}>—</span>
        </div>
      </div>

      <section className={styles.section}>
        <small className={styles.sectionLabel}>职责</small>
        <p className={styles.sectionBody}>{seat.responsibility || "未填写"}</p>
      </section>

      {seat.skillLoadout.length > 0 ? (
        <section className={styles.section}>
          <small className={styles.sectionLabel}>Skill ({seat.skillLoadout.length})</small>
          <div className={styles.chipRow}>
            {skillVisible.map((skill) => (
              <span key={skill} className={styles.chip}>{skill}</span>
            ))}
            {skillExtra > 0 ? <span className={styles.chipMore}>+{skillExtra}</span> : null}
          </div>
        </section>
      ) : null}

      {seat.knowledgeSummary ? (
        <section className={styles.section}>
          <small className={styles.sectionLabel}>知识库摘要</small>
          <p className={styles.sectionBody}>
            {showFullKnowledge ? seat.knowledgeSummary : knowledgePreview}
            {seat.knowledgeSummary.length > 80 ? (
              <button
                type="button"
                className={styles.inlineBtn}
                onClick={() => setShowFullKnowledge((v) => !v)}
              >
                {showFullKnowledge ? " 收起" : " 展开"}
              </button>
            ) : null}
          </p>
        </section>
      ) : null}

      <section className={styles.streamPlaceholder}>
        <small className={styles.sectionLabel}>关键消息流（S4 接入）</small>
        <div className={styles.streamHint}>
          <p>这里将显示 NPC 的关键操作流：派单标题、执行结果首句、最近错误。</p>
          <p className={styles.streamMuted}>当前阶段（S1）只渲染静态卡片信息。</p>
        </div>
      </section>

      <footer className={styles.foot}>
        <Link href={`/projects/${projectId}`} className={styles.linkBtn} title="跳到项目驾驶舱继续派单">
          去派单 →
        </Link>
        <span className={styles.footHint}>
          {seat.permissionLevel ? `权限：${seat.permissionLevel}` : ""}
        </span>
      </footer>
    </article>
  );
}
