import styles from "./common.module.css";

export function EmptyState({
  title,
  detail
}: {
  title: string;
  detail?: string;
}) {
  return (
    <div className={styles.emptyBox}>
      <p className={styles.titleLg}>{title}</p>
      {detail && <p className={styles.muted}>{detail}</p>}
    </div>
  );
}

