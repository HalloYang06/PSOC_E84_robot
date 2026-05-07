"use client";

import type { TeamNoticeToast as TeamNoticeToastData } from "../lib/use-team-notice-toast";

type Props = {
  toast: TeamNoticeToastData;
};

// 统一的团队动作 toast 视觉。固定屏幕顶部居中，成功绿底，带 role="status"。
// 不依赖 CSS module，避免两个壳各自维护样式。
export function TeamNoticeToast({ toast }: Props) {
  if (!toast) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-team-notice-toast={toast.id}
      style={{
        position: "fixed",
        top: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 9999,
        maxWidth: "min(640px, calc(100vw - 32px))",
        padding: "10px 16px",
        borderRadius: 999,
        background: "rgba(20, 56, 34, 0.92)",
        color: "#ddffd8",
        border: "1px solid rgba(115, 207, 126, 0.45)",
        fontSize: 13,
        fontWeight: 600,
        lineHeight: 1.4,
        boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
        pointerEvents: "none",
      }}
    >
      {toast.message}
    </div>
  );
}
