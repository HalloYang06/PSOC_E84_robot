import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PARTS = {
    ".gradle",
    ".pytest_cache",
    "__pycache__",
    "build",
    "install",
    "log",
    "node_modules",
}
FORBIDDEN_SUFFIXES = {
    ".apk",
    ".bin",
    ".db",
    ".elf",
    ".hex",
    ".map",
    ".pyc",
    ".sconsign.dblite",
    ".sqlite",
    ".sqlite3",
}


def tracked_paths():
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=True
    )
    return [Path(path) for path in output.split("\0") if path]


def is_forbidden(path):
    if any(path.as_posix().lower().endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return True

    forbidden_parts = FORBIDDEN_PARTS.intersection(path.parts)
    if path.parts[:2] == ("tools", "build"):
        forbidden_parts -= {"build"}

    return bool(forbidden_parts)


def is_ignored(path):
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", path.as_posix()],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def test_no_generated_or_runtime_artifacts_are_tracked():
    forbidden = [path for path in tracked_paths() if is_forbidden(path)]

    assert forbidden == []


def test_tools_build_source_is_allowed():
    path = Path("tools/build/rewrite-history.ps1")

    assert not is_forbidden(path)
    assert not is_ignored(path)


def test_generated_and_runtime_outputs_are_rejected():
    paths = (
        Path("firmware/m33/build/firmware.elf"),
        Path("firmware/m55/.sconsign.dblite"),
        Path("ros/rehab_arm_ws/build/package/file.o"),
        Path("ros/rehab_arm_ws/install/package/file"),
        Path("ros/rehab_arm_ws/log/latest/log.txt"),
        Path("apps/mobile/android/app/build/outputs/app.apk"),
        Path("platform/api/runtime.sqlite"),
        Path("platform/api/runtime.sqlite3"),
    )

    assert all(is_forbidden(path) for path in paths)
    assert all(is_ignored(path) for path in paths)


def test_design_document_exists():
    design = ROOT / "docs/superpowers/specs/2026-07-13-monorepo-migration-design.md"

    assert design.is_file()
