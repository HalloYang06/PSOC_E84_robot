"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import styles from "./common.module.css";
import { Button } from "./Button";

export function Dialog({
  open,
  title,
  children,
  confirmText = "确认",
  cancelText = "取消",
  confirmVariant = "primary",
  onCancel,
  onConfirm
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmText?: string;
  cancelText?: string;
  confirmVariant?: "default" | "primary" | "danger";
  onCancel: () => void;
  onConfirm?: () => void;
}) {
  const el = useMemo(() => {
    if (typeof document === "undefined") return null;
    return document.createElement("div");
  }, []);

  useEffect(() => {
    if (!el || typeof document === "undefined") return;
    document.body.appendChild(el);
    return () => {
      document.body.removeChild(el);
    };
  }, [el]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open || !el) return null;

  return createPortal(
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className={styles.dialog}>
        <div className={styles.cardHeader}>
          <h2 className={styles.dialogTitle}>{title}</h2>
          <Button onClick={onCancel} aria-label="close">
            关闭
          </Button>
        </div>
        <div className={styles.dialogBody}>{children}</div>
        <div className={styles.dialogFooter}>
          <Button onClick={onCancel}>{cancelText}</Button>
          {onConfirm && (
            <Button variant={confirmVariant} onClick={onConfirm}>
              {confirmText}
            </Button>
          )}
        </div>
      </div>
    </div>,
    el
  );
}

