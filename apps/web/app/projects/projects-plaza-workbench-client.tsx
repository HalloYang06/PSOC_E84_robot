"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";

import {
  acceptWorkspaceInvitation,
  createProjectWorkspace,
  sendWorkspaceInvitation,
  signOutWorkspace,
} from "../actions";
import styles from "./page.module.css";

type ProjectItem = {
  id: string;
  name: string;
  description: string;
  role: string;
  type: string;
  pendingHumanReviewCount: number;
  pendingHumanReviewTitle: string;
  pendingHumanReviewDetail: string;
  pendingHumanReviewLevel: string;
};

type InvitationItem = {
  id: string;
  projectName: string;
  note: string;
  role: string;
};

type TabId = "projects" | "invite" | "invites" | "create";
const tabs: Array<{ id: TabId; label: string; detail: string }> = [
  { id: "projects", label: "项目", detail: "进入项目与模式" },
  { id: "invite", label: "邀请", detail: "添加合作者" },
  { id: "invites", label: "收到", detail: "接受项目邀请" },
  { id: "create", label: "新建", detail: "创建项目空间" },
];

function isTabId(value: string | null): value is TabId {
  return value === "projects" || value === "invite" || value === "invites" || value === "create";
}

function canInvite(project: ProjectItem) {
  const role = project.role.trim().toLowerCase();
  return role === "owner" || role === "admin" || role === "maintainer" || role.includes("owner");
}

function roleLabel(role: string) {
  const normalized = role.trim().toLowerCase();
  if (normalized === "owner") return "项目负责人";
  if (normalized === "admin") return "管理员";
  if (normalized === "maintainer") return "维护者";
  if (normalized === "viewer") return "观察者";
  return "协作者";
}

function typeLabel(type: string) {
  const normalized = type.trim().toLowerCase();
  if (normalized === "education") return "教育项目";
  if (normalized === "hardware") return "硬件项目";
  return "软件项目";
}

function SubmitButton({ children, pendingLabel, className }: { children: ReactNode; pendingLabel: string; className: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={className} disabled={pending} aria-busy={pending}>
      {pending ? <span className={styles.plazaSpinner} aria-hidden="true" /> : null}
      {pending ? pendingLabel : children}
    </button>
  );
}

export function ProjectsPlazaWorkbench({
  user,
  projects,
  invitations,
  workspaceError,
  workspaceNotice,
}: {
  user: { name: string; email: string };
  projects: ProjectItem[];
  invitations: InvitationItem[];
  workspaceError?: string;
  workspaceNotice?: string;
}) {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>("projects");
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id ?? "");

  useEffect(() => {
    const tab = searchParams?.get("tab") ?? null;
    const projectId = searchParams?.get("project_id") ?? "";
    if (isTabId(tab)) setActiveTab(tab);
    if (projectId) setSelectedProjectId(projectId);
  }, [searchParams]);

  const inviteProjects = useMemo(() => projects.filter(canInvite), [projects]);
  const reviewCount = useMemo(
    () => projects.reduce((sum, project) => sum + project.pendingHumanReviewCount, 0),
    [projects],
  );
  const selectedInviteProject = inviteProjects.find((project) => project.id === selectedProjectId) ?? inviteProjects[0] ?? null;
  const highlightedProject =
    projects.find((project) => project.pendingHumanReviewCount > 0) ??
    projects.find((project) => project.id === selectedProjectId) ??
    projects[0] ??
    null;

  const nextAction = highlightedProject
    ? highlightedProject.pendingHumanReviewCount > 0
      ? `先处理 ${highlightedProject.name} 的 ${highlightedProject.pendingHumanReviewCount} 条人工审核。`
      : `进入 ${highlightedProject.name}，继续绑定电脑、NPC 和协作线程。`
    : "先创建一个项目，再邀请成员和接入电脑。";

  return (
    <main className={styles.plazaPage}>
      <section className={styles.plazaHero}>
        <div>
          <p className={styles.plazaEyebrow}>小A工作室 · 项目管理</p>
          <h1>选择项目，进入 AI 协作工作台。</h1>
          <p>
            这里只保留项目、成员和入口选择。真正的开发协作从项目工作台开始，由 Boss NPC 拆解目标并派给各工位 NPC。
          </p>
        </div>
        <form action={signOutWorkspace}>
          <button className={styles.plazaGhostButton} type="submit">退出登录</button>
        </form>
      </section>

      <section className={styles.plazaCommand}>
        <div className={styles.plazaProfile}>
          <span className={styles.plazaAvatar}>A</span>
          <div>
            <p>当前账号</p>
            <strong>{user.name || "未命名成员"}</strong>
            <small>{user.email || "未绑定邮箱"}</small>
          </div>
        </div>
        <div className={styles.plazaStats}>
          <article><strong>{projects.length}</strong><span>项目</span></article>
          <article><strong>{inviteProjects.length}</strong><span>可邀请</span></article>
          <article><strong>{invitations.length}</strong><span>待接受</span></article>
          <article><strong>{reviewCount}</strong><span>人工审核</span></article>
        </div>
        <div className={styles.plazaNextAction}>
          <span>当前推荐动作</span>
          <p>{nextAction}</p>
        </div>
      </section>

      {(workspaceError || workspaceNotice) && (
        <section className={workspaceError ? styles.plazaError : styles.plazaNotice}>
          {workspaceError || workspaceNotice}
        </section>
      )}

      <section className={styles.plazaWorkspace}>
        <nav className={styles.plazaTabs} aria-label="项目管理分区">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? styles.plazaTabActive : styles.plazaTab}
              onClick={() => setActiveTab(tab.id)}
            >
              <strong>{tab.label}</strong>
              <span>{tab.detail}</span>
            </button>
          ))}
        </nav>

        <div className={styles.plazaPanel}>
          {activeTab === "projects" && (
            <section className={styles.plazaProjectGrid}>
              {projects.length === 0 ? (
                <div className={styles.plazaEmpty}>
                  <h2>还没有项目</h2>
                  <p>先新建一个项目，然后再邀请合作者、添加电脑和创建 NPC。</p>
                  <button type="button" className={styles.plazaPrimaryButton} onClick={() => setActiveTab("create")}>新建项目</button>
                </div>
              ) : (
                projects.map((project) => (
                  <article className={styles.plazaProjectCard} key={project.id}>
                    <div className={styles.plazaProjectHead}>
                      <span>{typeLabel(project.type)}</span>
                      <span>{roleLabel(project.role)}</span>
                    </div>
                    <h2>{project.name}</h2>
                    <p>{project.description || "这个项目还没有填写说明。"}</p>
                    {project.pendingHumanReviewCount > 0 ? (
                      <div className={styles.plazaReviewBadge}>
                        需要人工审核：{project.pendingHumanReviewTitle || `${project.pendingHumanReviewCount} 条`}
                      </div>
                    ) : null}
                    <div className={styles.plazaProjectActions}>
                      <Link className={styles.plazaPrimaryButton} href={`/projects/${encodeURIComponent(project.id)}/2d-upgrade`}>
                        进入项目主页面
                      </Link>
                      {canInvite(project) ? (
                        <button
                          type="button"
                          className={styles.plazaTextButton}
                          onClick={() => {
                            setSelectedProjectId(project.id);
                            setActiveTab("invite");
                          }}
                        >
                          邀请成员
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))
              )}
            </section>
          )}

          {activeTab === "invite" && (
            <section className={styles.plazaFormLayout}>
              <div>
                <p className={styles.plazaEyebrow}>邀请合作者</p>
                <h2>把另一个账号加入当前项目</h2>
                <p>只有项目负责人、管理员或维护者可以邀请。被邀请的人登录后会在“收到”里接受邀请。</p>
              </div>
              <form action={sendWorkspaceInvitation} className={styles.plazaForm}>
                <input type="hidden" name="return_to" value="/projects?tab=invite" />
                <label>
                  <span>项目</span>
                  <select name="project_id" value={selectedInviteProject?.id ?? ""} onChange={(event) => setSelectedProjectId(event.target.value)} required>
                    {inviteProjects.map((project) => (
                      <option key={project.id} value={project.id}>{project.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>对方邮箱</span>
                  <input name="email" type="email" placeholder="partner@example.com" required />
                </label>
                <label>
                  <span>角色</span>
                  <select name="role" defaultValue="member">
                    <option value="member">协作者</option>
                    <option value="maintainer">维护者</option>
                    <option value="viewer">观察者</option>
                  </select>
                </label>
                <label>
                  <span>说明</span>
                  <textarea name="note" placeholder="告诉对方要负责什么，例如：只读验收 Unity 入口。" rows={4} />
                </label>
                <SubmitButton className={styles.plazaPrimaryButton} pendingLabel="正在发送邀请...">发送邀请</SubmitButton>
              </form>
            </section>
          )}

          {activeTab === "invites" && (
            <section className={styles.plazaInviteList}>
              {invitations.length === 0 ? (
                <div className={styles.plazaEmpty}>
                  <h2>暂无待接受邀请</h2>
                  <p>如果别人邀请你加入项目，登录后会在这里看到。</p>
                </div>
              ) : (
                invitations.map((invitation) => (
                  <article className={styles.plazaInviteCard} key={invitation.id}>
                    <div>
                      <span>{invitation.role}</span>
                      <h2>{invitation.projectName}</h2>
                      <p>{invitation.note}</p>
                    </div>
                    <form action={acceptWorkspaceInvitation.bind(null, invitation.id)}>
                      <SubmitButton className={styles.plazaPrimaryButton} pendingLabel="正在加入...">接受邀请</SubmitButton>
                    </form>
                  </article>
                ))
              )}
            </section>
          )}

          {activeTab === "create" && (
            <section className={styles.plazaFormLayout}>
              <div>
                <p className={styles.plazaEyebrow}>新建项目</p>
                <h2>从一个干净项目空间开始</h2>
                <p>项目创建后进入工作台：先创建 Boss/NPC、绑定线程，再开始自动化协作。</p>
              </div>
              <form action={createProjectWorkspace} className={styles.plazaForm}>
                <input type="hidden" name="project_type" value="software" />
                <label>
                  <span>项目名</span>
                  <input name="name" placeholder="例如：机器人协作开发" required />
                </label>
                <label>
                  <span>项目说明</span>
                  <textarea name="description" placeholder="用一句话说明这个项目要做什么。" rows={4} />
                </label>
                <label>
                  <span>GitHub 地址（可选）</span>
                  <input name="github_url" placeholder="https://github.com/owner/repo" />
                </label>
                <label>
                  <span>本机路径（可选）</span>
                  <input name="local_git_url" placeholder="D:/your/local/project" />
                </label>
                <div className={styles.plazaFormRow}>
                  <label>
                    <span>主分支</span>
                    <input name="default_branch" defaultValue="main" />
                  </label>
                  <label>
                    <span>开发分支</span>
                    <input name="develop_branch" defaultValue="develop" />
                  </label>
                </div>
                <SubmitButton className={styles.plazaPrimaryButton} pendingLabel="正在创建项目...">创建项目</SubmitButton>
              </form>
            </section>
          )}
        </div>
      </section>

      <footer className={styles.plazaFooter}>
        <span>建议下一步：进入工作台，让 Boss NPC 把一句话目标拆成可执行分工。</span>
      </footer>
    </main>
  );
}
