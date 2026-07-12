import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    ROOT / "docs/architecture/system-overview.md",
    ROOT / "docs/protocols/can-protocol.md",
    ROOT / "docs/protocols/m33-m55-ipc.md",
    ROOT / "docs/protocols/app-api.md",
    ROOT / "docs/protocols/safety-boundary.md",
]
REPOSITORY_PATH = re.compile(
    r"`((?:firmware|ros|apps|platform|ai|docs|tools)/[^`]+)`"
)


def test_architecture_and_protocol_documents_exist() -> None:
    assert [str(path.relative_to(ROOT)) for path in DOCS if not path.is_file()] == []


def test_documented_repository_paths_exist() -> None:
    missing: list[tuple[str, str]] = []
    for document in DOCS:
        text = document.read_text(encoding="utf-8")
        for repository_path in REPOSITORY_PATH.findall(text):
            if not (ROOT / repository_path).exists():
                missing.append((str(document.relative_to(ROOT)), repository_path))
    assert missing == []


def test_repository_path_parser_includes_tools_paths() -> None:
    text = DOCS[0].read_text(encoding="utf-8")
    assert "tools/bench-debug/legacy-5dof/README.md" in REPOSITORY_PATH.findall(text)


def test_ipc_snapshot_timestamp_unit_matches_producer() -> None:
    text = DOCS[2].read_text(encoding="utf-8")
    format_section = text.split("## Format, units, and version", 1)[1].split(
        "## Implementation links", 1
    )[0]
    assert "rt_tick_get_millisecond" in format_section
    assert "rt_tick_t" in format_section
    assert "\u6beb\u79d2" in format_section


def test_system_overview_keeps_required_sections() -> None:
    text = DOCS[0].read_text(encoding="utf-8")
    required = [
        "# System overview",
        "## Product layers",
        "## Hardware and runtime ownership",
        "## Formal motion path",
        "## Telemetry and model-result path",
        "## Mainline vs simulation/bench",
        "## Current verified capability",
        "## Known incomplete capability",
    ]
    assert [heading for heading in required if heading not in text] == []


def test_protocol_documents_keep_contract_sections_and_safety_boundary() -> None:
    required = [
        "## Owner",
        "## Consumers and direction",
        "## Format, units, and version",
        "## Implementation links",
        "## Tests",
        "## Failure behavior",
        "## Safety restrictions",
    ]
    for document in DOCS[1:]:
        text = document.read_text(encoding="utf-8")
        assert [heading for heading in required if heading not in text] == []

    safety_text = DOCS[-1].read_text(encoding="utf-8")
    assert "M33_ARCHITECTURAL_FINAL_SAFETY_AUTHORITY" in safety_text
    assert "SET_TARGET_PREARM_RECHECK_GAP" in safety_text
    assert "ctrl_assess_ros_command_safety" in safety_text
    assert "firmware/m33/applications/control/control_layer.c" in safety_text
    assert "`SET_TARGET`" in safety_text
    assert "pre-arm" in safety_text
    assert "current mode" in safety_text
    assert "SET_TARGET_DOES_NOT_RECHECK_FULL_PREARM_OR_CURRENT_MODE" in safety_text
    for command in ("`move:*`", "`mode:*`", "`stop`", "`ERR:readonly`"):
        assert command in safety_text
