import type { ReactNode } from "react";
import styles from "./common.module.css";

export function Card({
  title,
  right,
  children
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.card}>
      {(title || right) && (
        <div className={styles.cardHeader}>
          <div className={styles.cardTitle}>{title}</div>
          <div>{right}</div>
        </div>
      )}
      {children}
    </section>
  );
}

