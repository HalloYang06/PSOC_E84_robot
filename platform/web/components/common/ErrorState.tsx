import styles from "./common.module.css";

export function ErrorState({
  title,
  detail
}: {
  title: string;
  detail?: string;
}) {
  return (
    <div className={styles.emptyBox} style={{ borderStyle: "solid" }}>
      <p className={styles.titleLg}>{title}</p>
      {detail && <p className={styles.muted}>{detail}</p>}
    </div>
  );
}

