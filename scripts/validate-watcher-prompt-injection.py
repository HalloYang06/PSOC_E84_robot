#!/usr/bin/env python
"""
Step 7 验收：watcher 派给 Claude/Codex 之前，是否注入了
- recipient_id / seat_id（让 NPC 知道自己是谁）
- docs/npcs/<seat-id>/ 三层文档约定
- GitHub-link + Markdown 回复约定

直接 import adapter 的两个函数，不依赖 API 服务。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "scripts" / "platform-workstation-adapter.py"

spec = importlib.util.spec_from_file_location("platform_workstation_adapter", ADAPTER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return {"name": name, "ok": ok, "detail": detail}


def main() -> int:
    print("=" * 60)
    print("Step 7 验收：watcher prompt 注入")
    print("=" * 60)

    fake_command = {
        "id": "msg_demo_1",
        "title": "请把首页 nav 加一个登出按钮",
        "body": "右上角加「登出」，调 /api/auth/logout，跳回 /login。",
        "recipient_id": "seat_frontend_alice",
        "message_type": "agent_command",
        "status": "queued",
        "requirement_id": None,
    }

    md = mod._command_markdown(
        fake_command,
        project_id="proj_ai_collab",
        workstation_id="frontend-thread",
        provider="claude",
        computer_node_id="dev-laptop-01",
    )

    results = []
    print("\n[A] _command_markdown 注入项")
    results.append(_check("envelope 出现 recipient_id", "recipient_id" in md))
    results.append(_check("envelope 出现 seat_id 行", "seat_id (your NPC identity for docs)" in md))
    results.append(_check("seat_id 值就是 recipient_id", "`seat_frontend_alice`" in md))
    results.append(_check("提到 docs/npcs/<seat-id>/ 路径", "docs/npcs/seat_frontend_alice/" in md))
    results.append(_check("工位路径用 computer_node_id 拼（不是 thread config_id）", "docs/workstations/dev-laptop-01.md" in md))
    results.append(_check("envelope 暴露 computer_node_id", "computer_node_id: `dev-laptop-01`" in md))
    results.append(_check("提到 docs/projects/<id>/README.md", "docs/projects/<project-id>/README.md" in md))
    results.append(_check("约定 GitHub-flavored Markdown 回复", "GitHub-flavored Markdown" in md))
    results.append(_check("约定给 GitHub 链接（blob/branch/path）", "blob/<branch>/<path>" in md))
    results.append(_check("用户指令原文保留", "登出按钮" in md and "登出" in md))

    prompt = mod._extract_executor_prompt(md)
    print("\n[B] _extract_executor_prompt 注入项（实际进 Claude/Codex 的）")
    results.append(_check("prompt 提到岗位手册路径", "docs/npcs/seat_frontend_alice/" in prompt))
    results.append(_check("prompt 工位路径用 computer_node_id", "docs/workstations/dev-laptop-01.md" in prompt))
    results.append(_check("prompt 提到项目级背景", "docs/projects/<project-id>/README.md" in prompt))
    results.append(_check("prompt 强调 GitHub 链接", "GitHub" in prompt and "链接" in prompt))
    results.append(_check("prompt 强调 Markdown 回复", "Markdown" in prompt))
    results.append(_check("prompt 不再调平台 API", "不要再调用平台 API" in prompt))
    results.append(_check("prompt 还在传用户指令原文", "登出" in prompt))

    md2 = mod._command_markdown(
        {**fake_command, "recipient_id": ""},
        project_id="proj_ai_collab",
        workstation_id="frontend-thread",
        provider="claude",
        computer_node_id="dev-laptop-01",
    )
    print("\n[C] recipient_id 缺失时回落到 workstation_id")
    results.append(_check("缺 recipient_id 时 seat_id 兜底为 workstation_id",
                          "docs/npcs/frontend-thread/" in md2))

    md3 = mod._command_markdown(
        fake_command,
        project_id="proj_ai_collab",
        workstation_id="frontend-thread",
        provider="claude",
        # 不传 computer_node_id —— 模拟未绑节点
    )
    print("\n[D] computer_node_id 缺失时给出'尚未绑定'提示而不是错路径")
    results.append(_check("不绑节点时不能再用 thread config_id 拼工位路径",
                          "docs/workstations/frontend-thread.md" not in md3))
    results.append(_check("不绑节点时给出明确占位",
                          "<computer_node_id>" in md3 and "not yet bound" in md3))

    print("\n" + "=" * 60)
    failed = [r for r in results if not r["ok"]]
    if failed:
        print(f"❌ FAIL — {len(failed)}/{len(results)} 项不通过")
        for r in failed:
            print(f"  · {r['name']}")
        return 1
    print(f"✅ PASS — {len(results)}/{len(results)} 项全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
