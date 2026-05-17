from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"Missing {label}: {needle}")


def assert_not_contains(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"Unexpected {label}: {needle}")


def main() -> int:
    commands = read("apps/web/lib/runner-onboarding-commands.ts")
    download_route = read("apps/web/app/downloads/runner/[script]/route.ts")
    shell = read("apps/web/app/projects/[id]/project-playable-shell.tsx")
    connect_sh = read("scripts/connect-ai-collab-runner.sh")
    register_sh = read("scripts/register-runner.sh")
    codex_sync_sh = read("scripts/sync-codex-session-threads.sh")
    claude_sync_sh = read("scripts/sync-claude-session-threads.sh")
    manual_sync_sh = read("scripts/sync-runner-threads.sh")

    for script in (
        "register-runner.sh",
        "connect-ai-collab-runner.sh",
        "sync-runner-threads.sh",
        "sync-codex-session-threads.sh",
        "sync-claude-session-threads.sh",
    ):
      assert_contains(download_route, script, f"download allowlist entry for {script}")

    for export_name in (
        "buildRunnerApiBaseUrl",
        "buildComputerOneClickConnectBashCommand",
        "buildComputerRunnerWatchBashCommand",
        "buildComputerRunnerWatchServiceCommand",
        "buildComputerRunnerWatchServiceBashCommand",
        "buildComputerRunnerRegisterBashCommand",
        "buildWorkstationAdapterBashCommand",
        "buildComputerCodexThreadSyncBashCommand",
        "buildComputerClaudeThreadSyncBashCommand",
        "buildComputerManualThreadSyncBashCommand",
    ):
        assert_contains(commands, f"export function {export_name}", f"{export_name} export")
        if export_name != "buildRunnerApiBaseUrl":
            assert_contains(shell, export_name, f"{export_name} UI usage")

    for token in (
        '.replace(/:3001$/, ":8011")',
        '.replace(/:8011$/, ":3001")',
        "const apiBaseUrl = buildRunnerApiBaseUrl(serverUrl);",
    ):
        assert_contains(commands, token, f"cloud 3001/8011 normalization token {token}")

    for script_name in (
        "register-runner.ps1",
        "connect-ai-collab-runner.ps1",
        "sync-codex-session-threads.ps1",
        "sync-claude-session-threads.ps1",
        "sync-runner-threads.ps1",
    ):
        assert_contains(read(f"scripts/{script_name}"), ':3001$', f"{script_name} accepts cloud web port 3001")
        assert_contains(read(f"scripts/{script_name}"), ':8011', f"{script_name} resolves to cloud API port 8011")
        assert_not_contains(read(f"scripts/{script_name}"), ':3000$", ":8010', f"{script_name} old 3000 to 8010 mapping")

    for script_name in (
        "register-runner.sh",
        "connect-ai-collab-runner.sh",
        "sync-codex-session-threads.sh",
        "sync-claude-session-threads.sh",
        "sync-runner-threads.sh",
    ):
        assert_contains(read(f"scripts/{script_name}"), ":3001", f"{script_name} accepts cloud web port 3001")
        assert_contains(read(f"scripts/{script_name}"), ":8011", f"{script_name} resolves to cloud API port 8011")
        assert_not_contains(read(f"scripts/{script_name}"), ":3000/:8010", f"{script_name} old 3000 to 8010 mapping")

    retired_redirects = {
        "apps/web/app/projects/[id]/unity-client/page.tsx": "/robotics",
    }
    for rel in (
        "apps/web/app/projects/[id]/page.tsx",
        "apps/web/app/projects/[id]/project-playable-shell.tsx",
        "apps/web/app/projects/[id]/2d-upgrade/page.tsx",
        "apps/web/app/projects/[id]/company/page.tsx",
        "apps/web/app/projects/[id]/unity-client/page.tsx",
    ):
        source = read(rel)
        if rel in retired_redirects:
            assert_contains(source, "redirect(", f"{rel} retired route redirect")
            assert_contains(source, retired_redirects[rel], f"{rel} canonical route")
        else:
            assert_contains(source, "8011", f"{rel} production API fallback")
        assert_not_contains(source, "127.0.0.1:8010", f"{rel} stale local API fallback")

    for test_attr in (
        "data-computer-one-click-connect-linux-command",
        "data-computer-watch-linux-command",
        "data-computer-watch-service-command",
        "data-computer-watch-service-linux-command",
        "data-computer-watch-execute-linux-command",
        "data-computer-codex-sync-linux-command",
        "data-computer-claude-sync-linux-command",
        "data-computer-manual-sync-linux-command",
        "data-adapter-linux-command",
        "data-token-linux-command",
        "data-token-linux-watch-command",
    ):
        assert_contains(shell, test_attr, f"{test_attr} surface")

    for token in (
        "接入成功后要持续接单",
        "后台守护 / 开机自启",
        "默认只做最小回执和本机任务提示",
        "linuxCommand={pairingBashCommand}",
        "linuxWatchCommand={pairingWatchBashCommand}",
    ):
        assert_contains(shell, token, f"safe pairing token card text {token}")

    assert_not_contains(shell, "高风险持续执行命令", "unsafe first pairing watch token label")
    assert_contains(shell, "data-token-desktop-watch-card", "desktop-visible dispatch command is separated from safe watch")
    assert_contains(shell, "真实硬件、部署、Git 回退等高风险动作仍然需要人工确认", "desktop-visible dispatch safety copy")
    assert_contains(shell, "{ watch: true }", "safe watch command remains the default pairing watch")
    assert_contains(shell, "扫描到线程只代表平台看见过线程，不代表 runner 正在接单", "runner persistence state copy")

    for token in (
        "New-ScheduledTaskAction",
        "Register-ScheduledTask",
        "Start-ScheduledTask",
        "-EncodedCommand",
        "systemctl --user enable --now",
        "nohup bash -lc",
        "already-bound-runner-reuse",
    ):
        assert_contains(commands, token, f"persistent runner command token {token}")

    for token in (
        "curl -fsSL",
        "--server",
        "--pairing-token",
        "--computer-node-id",
        "--runner-id",
        "--project-id",
        "--watch",
        "platform-workstation-adapter.py",
        "sync-codex-session-threads.sh",
        "sync-claude-session-threads.sh",
        "the runner will retry automatically",
        "Consecutive failed loop(s)",
        "Runner watch recovered",
    ):
        assert_contains(connect_sh, token, f"connect bash token {token}")

    connect_ps1 = read("scripts/connect-ai-collab-runner.ps1")
    for token in (
        "Runner watch loop failed",
        "Runner watch is still active",
        "Consecutive failed loop(s)",
        "Runner watch recovered",
    ):
        assert_contains(connect_ps1, token, f"connect PowerShell retry token {token}")

    for token in ("curl -fsSL", "--server", "--pairing-token", "--computer-node-id", "--runner-name"):
        assert_contains(register_sh, token, f"register bash token {token}")

    for script_name, script_text in (
        ("sync-codex-session-threads.sh", codex_sync_sh),
        ("sync-claude-session-threads.sh", claude_sync_sh),
        ("sync-runner-threads.sh", manual_sync_sh),
    ):
        for token in ("thread-workstations/sync", "curl -fsSL", "x-runner-id", "--project-id", "--computer-node-id"):
            assert_contains(script_text, token, f"{script_name} token {token}")

    for script_name, script_text in (
        ("connect-ai-collab-runner.sh", connect_sh),
        ("register-runner.sh", register_sh),
        ("sync-codex-session-threads.sh", codex_sync_sh),
        ("sync-claude-session-threads.sh", claude_sync_sh),
        ("sync-runner-threads.sh", manual_sync_sh),
    ):
        if re.search(r"powershell|Invoke-WebRequest|\\.ps1", script_text, re.IGNORECASE):
            raise AssertionError(f"{script_name} should not depend on PowerShell or ps1")

    print(
        {
            "ok": True,
            "download_route": "allows ps1 and sh runner scripts",
            "ui": "shows Windows and Linux/macOS commands",
            "bash_scripts": "register/connect/watch entrypoints present",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
