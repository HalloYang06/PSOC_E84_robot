import type { ReactNode } from "react";
import type { ApprovalStatus, HardwareRiskLevel, HealthLevel } from "./types";

function clamp01(n: number) {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function Panel({
  title,
  subtitle,
  actions,
  children
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 10
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, justifyContent: "space-between" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {title}
          </div>
          {subtitle ? <div style={{ fontSize: 12, color: "var(--muted)" }}>{subtitle}</div> : null}
        </div>
        {actions ? <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>{actions}</div> : null}
      </div>
      <div>{children}</div>
    </section>
  );
}

export function Pill({
  label,
  tone = "neutral",
  title
}: {
  label: string;
  tone?: "neutral" | "info" | "ok" | "warn" | "danger";
  title?: string;
}) {
  const bg =
    tone === "ok"
      ? "rgba(63,185,80,0.18)"
      : tone === "warn"
        ? "rgba(210,153,34,0.18)"
        : tone === "danger"
          ? "rgba(248,81,73,0.18)"
          : tone === "info"
            ? "rgba(88,166,255,0.18)"
            : "rgba(154,164,175,0.16)";
  const fg =
    tone === "ok"
      ? "var(--accent)"
      : tone === "warn"
        ? "var(--warn)"
        : tone === "danger"
          ? "var(--danger)"
          : tone === "info"
            ? "var(--info)"
            : "var(--muted)";

  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 8,
        border: "1px solid var(--border)",
        background: bg,
        color: fg,
        fontSize: 12,
        lineHeight: "16px",
        whiteSpace: "nowrap"
      }}
    >
      {label}
    </span>
  );
}

export function Meter({
  label,
  value,
  tone,
  hint
}: {
  label: string;
  value: number; // 0..1
  tone: "ok" | "warn" | "danger" | "info" | "neutral";
  hint?: string;
}) {
  const v = clamp01(value);
  const fill =
    tone === "ok"
      ? "var(--accent)"
      : tone === "warn"
        ? "var(--warn)"
        : tone === "danger"
          ? "var(--danger)"
          : tone === "info"
            ? "var(--info)"
            : "var(--muted)";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "center" }} title={hint}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {label}
        </div>
        <div
          style={{
            height: 8,
            borderRadius: 8,
            background: "var(--panel-alt)",
            border: "1px solid var(--border)",
            overflow: "hidden"
          }}
        >
          <div style={{ width: `${Math.round(v * 100)}%`, height: "100%", background: fill }} />
        </div>
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", minWidth: 40, textAlign: "right" }}>{Math.round(v * 100)}%</div>
    </div>
  );
}

export function healthTone(h: HealthLevel): "ok" | "warn" | "danger" {
  if (h === "green") return "ok";
  if (h === "yellow") return "warn";
  return "danger";
}

export function riskTone(h: HardwareRiskLevel): "ok" | "warn" | "danger" | "neutral" {
  if (h === "H0") return "ok";
  if (h === "H1") return "neutral";
  if (h === "H2") return "warn";
  return "danger";
}

export function approvalTone(a: ApprovalStatus): "neutral" | "info" | "ok" | "danger" {
  if (a === "approved") return "ok";
  if (a === "rejected") return "danger";
  if (a === "pending") return "info";
  return "neutral";
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return (
    <div style={{ border: "1px dashed var(--border)", borderRadius: 8, padding: 12, color: "var(--muted)" }}>
      <div style={{ fontSize: 13, fontWeight: 650, color: "var(--text)" }}>{title}</div>
      {body ? <div style={{ fontSize: 12, marginTop: 6 }}>{body}</div> : null}
    </div>
  );
}

