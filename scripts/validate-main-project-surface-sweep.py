from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CAPTURE_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot.mjs"


@dataclass
class PageCheck:
    slug: str
    title: str
    path: str
    markers: list[str] = field(default_factory=list)
    no_auth: bool = False
    issues: list[str] = field(default_factory=list)
    screenshot: str | None = None
    text_dump: str | None = None
    html_dump: str | None = None
    status: str = "pending"
    error: str | None = None
    text_excerpt: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a screenshot-heavy validation sweep across the main project surfaces.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--project-id", default="10f6a858-f3e4-467c-87f5-726caa3cc2be")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1100)
    parser.add_argument("--capture-timeout", type=float, default=90.0)
    parser.add_argument(
        "--forbid-text",
        action="append",
        default=[],
        help="Text that must not appear on project-specific pages. Can be passed multiple times.",
    )
    return parser.parse_args()


def build_checks(project_id: str) -> list[PageCheck]:
    return [
        PageCheck("login", "登录页", "/login", markers=["登录", "进入平台"], no_auth=True),
        PageCheck("projects", "项目管理入口", "/projects?tab=projects", markers=["项目管理入口", "我的项目"]),
        PageCheck("project-map", "主项目地图页", f"/projects/{project_id}"),
        PageCheck("development-workshop", "开发工坊", f"/projects/{project_id}?panel=team&tab=development-workshop"),
        PageCheck("human-party", "主角协作管理", f"/projects/{project_id}?panel=team&tab=human-party"),
        PageCheck("npc-manager", "NPC 管理", f"/projects/{project_id}?panel=team&tab=npc-create"),
        PageCheck("computers", "电脑接入管理", f"/projects/{project_id}?panel=team&tab=computers"),
        PageCheck("skills", "Skill 管理仓库", f"/projects/{project_id}?panel=team&tab=skills"),
        PageCheck("schedule", "日程日历", f"/projects/{project_id}?panel=team&tab=schedule"),
        PageCheck("serial-tv", "串口电视", f"/projects/{project_id}?panel=team&tab=serial-tv"),
        PageCheck("exchange", "协作消息池", f"/projects/{project_id}?panel=team&tab=exchange"),
        PageCheck("machine-room", "线程调试", f"/projects/{project_id}?panel=team&tab=machine-room"),
        PageCheck("git", "Git 协作与回退", f"/projects/{project_id}?panel=team&tab=git"),
    ]


def run_capture(
    check: PageCheck,
    *,
    web_base: str,
    login_email: str,
    login_password: str,
    output_dir: Path,
    stamp: str,
    viewport_width: int,
    viewport_height: int,
    capture_timeout: float,
    forbid_text: list[str],
) -> None:
    screenshot_path = output_dir / f"surface-sweep-{check.slug}-{stamp}.png"
    text_dump_path = output_dir / f"surface-sweep-{check.slug}-{stamp}.txt"
    html_dump_path = output_dir / f"surface-sweep-{check.slug}-{stamp}.html"
    url = f"{web_base.rstrip('/')}{check.path}"

    command = [
        "node",
        str(CAPTURE_SCRIPT),
        "--url",
        url,
        "--output",
        str(screenshot_path),
        "--text-dump",
        str(text_dump_path),
        "--html-dump",
        str(html_dump_path),
        "--viewport-width",
        str(viewport_width),
        "--viewport-height",
        str(viewport_height),
        "--wait-ms",
        "4500",
    ]
    if check.markers:
        command.extend(["--markers", "|".join(check.markers)])
    if check.no_auth:
        command.extend(["--no-auth", "true"])
    else:
        command.extend(
            [
                "--login-email",
                login_email,
                "--login-password",
                login_password,
                "--expected-url-contains",
                check.path,
            ]
        )

    check.screenshot = str(screenshot_path)
    check.text_dump = str(text_dump_path)
    check.html_dump = str(html_dump_path)

    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=capture_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        check.status = "failed"
        check.error = f"capture timed out after {capture_timeout:.0f}s: {exc}"
        return

    if completed.returncode != 0:
        check.status = "failed"
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        check.error = stderr or stdout or f"capture exited with {completed.returncode}"
        return

    body_text = text_dump_path.read_text(encoding="utf-8", errors="replace") if text_dump_path.exists() else ""
    check.text_excerpt = body_text[:600]
    check.status = "ok"
    detect_issues(check, body_text, forbid_text=forbid_text)


def detect_issues(check: PageCheck, body_text: str, *, forbid_text: list[str]) -> None:
    normalized = body_text.replace("\r\n", "\n")
    lowered = normalized.lower()

    if "application error" in lowered or "client-side exception" in lowered:
        check.issues.append("页面出现前端崩溃提示。")
    if "无法访问此页面" in normalized or "拒绝连接" in normalized or "err_connection_refused" in lowered:
        check.issues.append("页面打开失败，出现连接或访问错误。")
    if "no_body" in lowered or not normalized.strip():
        check.issues.append("页面正文为空，像是没有成功渲染。")

    if check.slug == "project-map" and "项目主角" in normalized and "条共享任务" in normalized:
        check.issues.append("地图页仍然出现展开式项目主角信息块，需要继续核对是否遮挡视野。")

    if check.slug == "exchange":
        has_second_level_nav = any(marker in normalized for marker in ("二级快速定位", "协作分区栏", "二级对象栏"))
        if "下发协作指令" in normalized and "总览与入口" not in normalized:
            check.issues.append("协作消息池打开后仍直接掉进派工表单，一级总览不够稳定。")
        if not has_second_level_nav:
            check.issues.append("协作消息池缺少二级定位栏，结构可能退回旧形态。")

    if check.slug == "human-party" and "主角协作管理" not in normalized:
        check.issues.append("主角协作管理入口没有稳定落在当前页面。")
    if check.slug == "projects" and "项目管理入口" not in normalized:
        check.issues.append("项目管理页没有稳定显示项目管理入口文案。")

    project_specific = check.slug not in {"login", "projects"}
    if project_specific:
        for marker in forbid_text:
            if marker and marker in normalized:
                check.issues.append(f"项目专属页面出现禁止残留文本：{marker}")


def build_markdown_report(report_path: Path, checks: list[PageCheck], stamp: str) -> None:
    lines = [
        f"# 主项目表面巡检报告 {stamp}",
        "",
        "这轮目标：按真实用户入口逐页截图，记录异常、结构退化和明显不合理点。",
        "",
    ]
    for check in checks:
        lines.append(f"## {check.title}")
        lines.append(f"- 状态：`{check.status}`")
        lines.append(f"- 路径：`{check.path}`")
        if check.screenshot:
            lines.append(f"- 截图：[{Path(check.screenshot).name}]({check.screenshot})")
        if check.text_dump:
            lines.append(f"- 文本：[{Path(check.text_dump).name}]({check.text_dump})")
        if check.error:
            lines.append(f"- 错误：`{check.error}`")
        if check.issues:
            lines.append("- 记录的问题：")
            for issue in check.issues:
                lines.append(f"  - {issue}")
        else:
            lines.append("- 记录的问题：无明显阻塞。")
        if check.text_excerpt:
            excerpt = check.text_excerpt.replace("\n", " ").strip()
            lines.append(f"- 文本摘要：`{excerpt[:220]}`")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks = build_checks(args.project_id)

    for check in checks:
        run_capture(
            check,
            web_base=args.web_base,
            login_email=args.login_email,
            login_password=args.login_password,
            output_dir=output_dir,
            stamp=stamp,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            capture_timeout=args.capture_timeout,
            forbid_text=args.forbid_text,
        )

    json_report_path = output_dir / f"surface-sweep-report-{stamp}.json"
    markdown_report_path = output_dir / f"surface-sweep-report-{stamp}.md"
    all_issues = [
        {"slug": check.slug, "title": check.title, "issue": issue}
        for check in checks
        for issue in check.issues
    ]
    failed = [check.slug for check in checks if check.status != "ok"]
    ok = not failed and not all_issues

    json_report_path.write_text(
        json.dumps(
            {
                "ok": ok,
                "generated_at": datetime.now().isoformat(),
                "web_base": args.web_base,
                "project_id": args.project_id,
                "failed": failed,
                "issue_count": len(all_issues),
                "issues": all_issues,
                "checks": [asdict(item) for item in checks],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    build_markdown_report(markdown_report_path, checks, stamp)

    print(
        json.dumps(
            {
                "ok": ok,
                "json_report": str(json_report_path),
                "markdown_report": str(markdown_report_path),
                "failed": failed,
                "issue_count": len(all_issues),
                "issues": all_issues,
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
