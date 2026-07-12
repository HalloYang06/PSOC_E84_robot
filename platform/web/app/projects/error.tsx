"use client";

import Link from "next/link";
import { useEffect } from "react";

import styles from "./page.module.css";

const PROJECTS_RUNTIME_RECOVERY_KEY = "ai-collab-projects-runtime-recovery-v1";

export default function ProjectsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Projects route error", error);
  }, [error]);

  return (
    <main className={styles.page}>
      <section className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.kicker}>项目管理入口恢复中</span>
          <h1>项目管理页刚刚走偏了，我们先把它拉回来。</h1>
          <p>
            这通常不是你的操作有问题，更常见的原因是浏览器拿着旧的前端 bundle 或失效的静态 chunk。
            先点一次刷新恢复；如果你刚经历过升级，这一步通常就能回来。
          </p>
          <div className={styles.commandActions}>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={() => {
                try {
                  window.sessionStorage.removeItem(PROJECTS_RUNTIME_RECOVERY_KEY);
                } catch {}
                reset();
              }}
            >
              重新加载项目管理页
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => window.location.reload()}
            >
              强制刷新当前页
            </button>
            <Link href="/login" className={styles.secondaryButton}>
              回登录页
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.noticeStack}>
        <div className={styles.errorBanner}>
          <strong>已拦截到前端异常。</strong>
          <div>{error?.message || "项目管理页发生了客户端异常。"}</div>
        </div>
      </section>
    </main>
  );
}
