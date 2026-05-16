"use client";

import { useState } from "react";

import styles from "./page.module.css";

type PasswordFieldProps = {
  autoComplete?: string;
  placeholder: string;
};

export function PasswordField({ autoComplete, placeholder }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className={styles.passwordControl}>
      <input
        name="password"
        type={visible ? "text" : "password"}
        placeholder={placeholder}
        required
        autoComplete={autoComplete}
      />
      <button
        type="button"
        className={styles.passwordToggle}
        aria-label={visible ? "隐藏密码" : "显示密码"}
        aria-pressed={visible}
        onClick={() => setVisible((value) => !value)}
      >
        {visible ? "隐藏" : "显示"}
      </button>
    </div>
  );
}
