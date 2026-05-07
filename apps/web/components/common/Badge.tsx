import styles from "./common.module.css";

type Tone = "green" | "yellow" | "orange" | "red" | "blue" | "gray";

export function Badge({
  tone = "gray",
  text,
  title
}: {
  tone?: Tone;
  text: string;
  title?: string;
}) {
  const dotCls = [
    styles.dot,
    tone === "green" ? styles.dotGreen : "",
    tone === "yellow" ? styles.dotYellow : "",
    tone === "orange" ? styles.dotOrange : "",
    tone === "red" ? styles.dotRed : "",
    tone === "blue" ? styles.dotBlue : "",
    tone === "gray" ? styles.dotGray : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={styles.badge} title={title}>
      <span className={dotCls} aria-hidden />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{text}</span>
    </span>
  );
}

