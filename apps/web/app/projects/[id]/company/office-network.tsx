"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./company.module.css";

export type OfficeNetworkNode = {
  id: string;
  name: string;
  x: number;
  y: number;
  outgoingCount: number;
  incomingCount: number;
  taskCount: number;
  tone: string;
  href: string;
};

export type OfficeNetworkEdge = {
  id: string;
  fromId: string;
  toId: string;
  count: number;
  label: string;
  needTone: string;
  taskTone: string;
  receiptTone: string;
  kind: "collaboration" | "relationship";
  href: string;
};

type OfficeNetworkProps = {
  projectId: string;
  nodes: OfficeNetworkNode[];
  edges: OfficeNetworkEdge[];
};

type Point = { x: number; y: number };

function clampPoint(point: Point): Point {
  return {
    x: Math.max(7, Math.min(93, point.x)),
    y: Math.max(9, Math.min(91, point.y)),
  };
}

export function OfficeNetwork({ projectId, nodes, edges }: OfficeNetworkProps) {
  const storageKey = `company-office-network:${projectId}:v2`;
  const mapRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef<{ id: string; pointerId: number; moved: boolean } | null>(null);
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [draggingId, setDraggingId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, Point>;
      const next: Record<string, Point> = {};
      for (const node of nodes) {
        const saved = parsed[node.id];
        if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) next[node.id] = clampPoint(saved);
      }
      setPositions(next);
    } catch {
      setPositions({});
    }
  }, [nodes, storageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(positions));
    } catch {
      // Drag positions are only a local view preference.
    }
  }, [positions, storageKey]);

  const nodeById = useMemo(() => {
    const map = new Map<string, OfficeNetworkNode & Point>();
    for (const node of nodes) {
      const position = positions[node.id] ?? { x: node.x, y: node.y };
      map.set(node.id, { ...node, ...clampPoint(position) });
    }
    return map;
  }, [nodes, positions]);

  const positionedNodes = useMemo(() => nodes.map((node) => nodeById.get(node.id)).filter(Boolean) as Array<OfficeNetworkNode & Point>, [nodeById, nodes]);

  function moveNode(id: string, clientX: number, clientY: number) {
    const rect = mapRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    const next = clampPoint({
      x: ((clientX - rect.left) / rect.width) * 100,
      y: ((clientY - rect.top) / rect.height) * 100,
    });
    setPositions((current) => ({ ...current, [id]: next }));
  }

  function resetLayout() {
    setPositions({});
  }

  return (
    <div className={styles.officeMap} ref={mapRef}>
      <button type="button" className={styles.officeResetBtn} onClick={resetLayout}>
        重排
      </button>
      <svg className={styles.officeSvg} viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="NPC 协作网络线">
        {edges.map((edge, index) => {
          const from = nodeById.get(edge.fromId);
          const to = nodeById.get(edge.toId);
          if (!from || !to) return null;
          const dx = to.x - from.x;
          const dy = to.y - from.y;
          const p1x = from.x + dx * 0.16;
          const p1y = from.y + dy * 0.16;
          const p2x = from.x + dx * 0.42;
          const p2y = from.y + dy * 0.42;
          const p3x = from.x + dx * 0.68;
          const p3y = from.y + dy * 0.68;
          const p4x = from.x + dx * 0.86;
          const p4y = from.y + dy * 0.86;
          const distance = Math.max(Math.hypot(dx, dy), 1);
          const normalX = -dy / distance;
          const normalY = dx / distance;
          const labelOffset = [-4.2, 0, 4.2, -7, 7][index % 5];
          const labelX = from.x + dx * 0.5 + normalX * labelOffset;
          const labelY = from.y + dy * 0.5 + normalY * labelOffset;
          const width = edge.kind === "relationship" ? 1.15 : Math.min(3.1, 1.35 + edge.count * 0.32);
          const edgeLabel = edge.kind === "relationship" ? `${edge.label}关系` : `${edge.count > 1 ? `${edge.count}条 ` : ""}${edge.label}`;
          return (
            <a key={edge.id} href={edge.href} className={styles.networkEdgeLink} data-kind={edge.kind} aria-label={`${from.name} 到 ${to.name}: ${edgeLabel}`}>
              <title>{`${from.name} → ${to.name}：${edgeLabel}`}</title>
              <line x1={p1x} y1={p1y} x2={p2x} y2={p2y} className={styles.networkEdgeHit} />
              <line x1={p2x} y1={p2y} x2={p3x} y2={p3y} className={styles.networkEdgeHit} />
              <line x1={p3x} y1={p3y} x2={p4x} y2={p4y} className={styles.networkEdgeHit} />
              <line x1={p1x} y1={p1y} x2={p2x} y2={p2y} className={styles.networkEdge} data-tone={edge.needTone} strokeWidth={width} />
              <line x1={p2x} y1={p2y} x2={p3x} y2={p3y} className={styles.networkEdge} data-tone={edge.taskTone} strokeWidth={width} />
              <line x1={p3x} y1={p3y} x2={p4x} y2={p4y} className={styles.networkEdge} data-tone={edge.receiptTone} strokeWidth={width} />
              <text x={labelX} y={labelY} className={styles.networkEdgeLabel}>
                {edgeLabel}
              </text>
            </a>
          );
        })}
      </svg>
      <div className={styles.officeNodeLayer}>
        {positionedNodes.map((node) => (
          <Link
            key={node.id}
            href={node.href}
            className={styles.officeNode}
            data-tone={node.tone}
            data-dragging={draggingId === node.id ? "1" : undefined}
            style={{ left: `${node.x}%`, top: `${node.y}%` }}
            draggable={false}
            onClick={(event) => {
              if (dragStartRef.current?.id === node.id && dragStartRef.current.moved) event.preventDefault();
            }}
            onPointerDown={(event) => {
              dragStartRef.current = { id: node.id, pointerId: event.pointerId, moved: false };
              setDraggingId(node.id);
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              const drag = dragStartRef.current;
              if (!drag || drag.id !== node.id || drag.pointerId !== event.pointerId) return;
              drag.moved = true;
              moveNode(node.id, event.clientX, event.clientY);
            }}
            onPointerUp={(event) => {
              if (dragStartRef.current?.pointerId === event.pointerId) {
                window.setTimeout(() => {
                  dragStartRef.current = null;
                }, 0);
              }
              setDraggingId(null);
            }}
            onPointerCancel={() => {
              dragStartRef.current = null;
              setDraggingId(null);
            }}
          >
            <b>{node.name.slice(0, 2).toUpperCase()}</b>
            <strong>{node.name}</strong>
            <span>{node.outgoingCount}/{node.incomingCount}/{node.taskCount}</span>
          </Link>
        ))}
      </div>
      {!edges.length ? (
        <div className={styles.emptyOfficeNetwork}>
          <strong>还没有 NPC 间协作线</strong>
          <p>NPC 创建 Need 并路由成 Task 后，这里会出现带颜色分段的协作线。</p>
        </div>
      ) : null}
    </div>
  );
}
