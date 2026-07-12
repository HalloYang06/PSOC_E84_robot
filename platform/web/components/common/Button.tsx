"use client";

import type { ButtonHTMLAttributes } from "react";
import styles from "./common.module.css";

type Variant = "default" | "primary" | "danger";

export function Button({
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const cls = [
    styles.btn,
    variant === "primary" ? styles.btnPrimary : "",
    variant === "danger" ? styles.btnDanger : ""
  ]
    .filter(Boolean)
    .join(" ");
  return <button {...props} className={cls} />;
}

