import Link from "next/link";
import { redirect } from "next/navigation";

import { 登录用户 as loginWorkspace, 注册用户 as registerWorkspace } from "../actions";
import { getCurrentAuthState } from "../../lib/server-data";
import styles from "./page.module.css";

type LoginPageProps = {
  searchParams?: {
    mode?: string;
    error?: string;
    returnTo?: string;
    next?: string;
  };
};

function getErrorText(error?: string) {
  if (!error) return "";
  if (error === "USER_EXISTS") return "这个邮箱已经注册过了，直接登录就可以。";
  if (error === "INVALID_CREDENTIALS") return "邮箱或密码不正确，请重新输入。";
  if (error === "USER_DISABLED") return "这个账号当前不可用，请联系管理员。";
  if (error === "REGISTER_FAILED") return "注册没有完成，请稍后再试。";
  if (error === "LOGIN_FAILED") return "登录没有完成，请稍后再试。";
  return "提交失败，请稍后再试。";
}

const capabilityItems = [
  "项目、账号、电脑、线程、NPC 数据互相隔离",
  "Boss NPC 把一句话目标拆成工位、NPC、skill 和验收口",
  "Codex、Claude、Qwen 等线程统一进入协作链路",
  "人工审核、自动化开关、最终回复池都回到项目内",
];

function isSafeLocalReturnPath(value: string) {
  if (!value || !value.startsWith("/")) return false;
  if (value.startsWith("//")) return false;
  if (/[\\\u0000-\u001f\u007f]/.test(value)) return false;
  return !/^[a-z][a-z0-9+.-]*:/i.test(value);
}

function normalizeLoginReturnPath(value?: string) {
  const decoded = value ? decodeURIComponent(value) : "";
  if (
    isSafeLocalReturnPath(decoded)
    && (
      decoded === "/projects"
      || decoded.startsWith("/projects/")
      || decoded.startsWith("/projects?")
      || decoded === "/members"
      || decoded.startsWith("/members?")
    )
  ) {
    return decoded;
  }
  return "";
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const returnTo = normalizeLoginReturnPath(searchParams?.returnTo ?? searchParams?.next);
  const authState = await getCurrentAuthState();
  const hasActiveSession = Boolean(authState.data?.user?.id ?? authState.data?.user?.email);

  if (hasActiveSession) {
    redirect(returnTo || "/projects");
  }

  const mode = searchParams?.mode === "signup" ? "signup" : "login";
  const errorText = getErrorText(searchParams?.error);
  const signupHref = returnTo ? `/login?mode=signup&returnTo=${encodeURIComponent(returnTo)}` : "/login?mode=signup";
  const loginHref = returnTo ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login";

  return (
    <main className={styles.page}>
      <div className={styles.sceneGlow} aria-hidden="true" />
      <section className={styles.hero}>
        <div className={styles.identityCard}>
          <span className={styles.avatarMark}>A</span>
          <div>
            <p>小A工作室</p>
            <strong>A Agent</strong>
          </div>
        </div>

        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>AI collaboration workspace</p>
          <h1>一句目标，启动你的 AI 协作团队。</h1>
          <p className={styles.subtitle}>
            先登录进入项目空间，再让 Boss NPC 拆解目标、建议 NPC 和 skill，并把任务派给绑定了 Codex / Claude Code 线程的工位。
          </p>
          <div className={styles.heroActions}>
            <a href="#auth" className={styles.primaryLink}>进入平台</a>
          </div>
        </div>

        <div className={styles.capabilityRail}>
          {capabilityItems.map((item, index) => (
            <div className={styles.capabilityItem} key={item}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{item}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="auth" className={styles.authPanel} aria-label="账号入口">
        <div className={styles.panelHeader}>
          <p className={styles.panelKicker}>{mode === "login" ? "继续工作" : "创建账号"}</p>
          <h2>{mode === "login" ? "登录小A工作室" : "创建小A工作室账号"}</h2>
          <p>
            {mode === "login"
              ? "登录后进入项目管理页，从那里新建项目、邀请协作者、绑定电脑和线程。"
              : "注册后会直接进入项目管理页；账号由项目隔离，后续也可以改成硬件发放账号。"}
          </p>
        </div>

        <div className={styles.switcher}>
          <Link className={mode === "login" ? styles.switchActive : styles.switchLink} href={loginHref}>登录</Link>
          <Link className={mode === "signup" ? styles.switchActive : styles.switchLink} href={signupHref}>注册</Link>
        </div>

        {errorText ? <div className={styles.errorBanner}>{errorText}</div> : null}

        {mode === "login" ? (
          <form action={loginWorkspace} className={styles.form}>
            <input type="hidden" name="return_to" value={returnTo} />
            <label className={styles.field}>
              <span>邮箱</span>
              <input name="email" type="email" placeholder="you@company.com" required autoComplete="email" />
            </label>
            <label className={styles.field}>
              <span>密码</span>
              <input name="password" type="password" placeholder="输入登录密码" required autoComplete="current-password" />
            </label>
            <button type="submit" className={styles.submitButton}>进入项目空间</button>
          </form>
        ) : (
          <form action={registerWorkspace} className={styles.form}>
            <input type="hidden" name="return_to" value={returnTo} />
            <label className={styles.field}>
              <span>显示名</span>
              <input name="name" placeholder="例如：小A开发者" required />
            </label>
            <label className={styles.field}>
              <span>邮箱</span>
              <input name="email" type="email" placeholder="you@company.com" required />
            </label>
            <label className={styles.field}>
              <span>密码</span>
              <input name="password" type="password" placeholder="至少 4 位密码" required />
            </label>
            <button type="submit" className={styles.submitButton}>创建账号并进入</button>
          </form>
        )}

        <p className={styles.securityNote}>
          登录态只用于当前平台；项目页会继续按账号和项目隔离协作数据。
        </p>
      </section>
    </main>
  );
}
