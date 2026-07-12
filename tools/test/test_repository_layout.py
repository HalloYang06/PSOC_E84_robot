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
RUNTIME_SUFFIXES = {
    ".apk",
    ".db",
    ".pyc",
    ".sqlite",
    ".sqlite3",
}
FIRMWARE_OUTPUT_SUFFIXES = {".bin", ".elf", ".hex", ".map"}
FIRMWARE_OUTPUT_DIRECTORIES = {"build", "out", "output", "outputs"}


def decode_tracked_paths(output):
    decoded = output.decode("utf-8", errors="surrogateescape")
    return [Path(path) for path in decoded.split("\0") if path]


def tracked_paths():
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return decode_tracked_paths(output)


def is_forbidden(path):
    normalized_parts = tuple(part.casefold() for part in path.parts)
    normalized_path = "/".join(normalized_parts)

    if any(
        normalized_path.endswith(suffix) for suffix in RUNTIME_SUFFIXES
    ):
        return True

    if normalized_parts[-1] == ".sconsign.dblite":
        return True

    is_firmware_output = Path(normalized_parts[-1]).suffix in FIRMWARE_OUTPUT_SUFFIXES
    is_firmware_path = normalized_parts[:1] == ("firmware",)
    is_component_root_output = is_firmware_path and len(normalized_parts) == 3
    is_generated_firmware_output = is_firmware_path and bool(
        FIRMWARE_OUTPUT_DIRECTORIES.intersection(normalized_parts[2:-1])
    )
    if is_firmware_output and (
        is_component_root_output or is_generated_firmware_output
    ):
        return True

    forbidden_parts = FORBIDDEN_PARTS.intersection(normalized_parts[:-1])
    if normalized_parts[:2] == ("tools", "build"):
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


def test_generated_directory_policy_is_case_insensitive():
    paths = (
        Path("ros/ws/BUILD/package/file.o"),
        Path("apps/mobile/NODE_MODULES/package/index.js"),
        Path("apps/mobile/.GRADLE/cache/metadata.bin"),
    )

    # Gitignore covers canonical lowercase paths; this tracked-file guard also
    # catches mixed-case artifacts consistently on case-sensitive and Windows hosts.
    assert all(is_forbidden(path) for path in paths)


def test_mixed_case_tools_build_source_is_allowed():
    assert not is_forbidden(Path("tools/Build/rewrite-history.ps1"))


def test_tracked_path_bytes_are_decoded_as_utf8():
    paths = decode_tracked_paths("docs/中文说明.md\0".encode("utf-8"))

    assert paths == [Path("docs/中文说明.md")]


def test_nested_vendor_firmware_resources_are_allowed():
    paths = (
        Path(
            "firmware/m33/libraries/components/wifi-host-driver/"
            "wifi-host-driver/WHD/COMPONENT_WIFI5/resources/firmware/"
            "COMPONENT_43012/43012C0-mfgtest.bin"
        ),
        Path(
            "firmware/m33/tools/edgeprotecttools/bin/_internal/"
            "edgeprotecttools/targets/pse8xs4/packets/apps/prov_oem/"
            "cyapp_prov_oem_signed_0.bin"
        ),
        Path(
            "firmware/m33/tools/edgeprotecttools/cm33_s_signed_fw/"
            "proj_cm33_s_signed.hex"
        ),
    )

    assert all(not is_forbidden(path) for path in paths)


def test_generated_and_runtime_outputs_are_rejected():
    paths = (
        Path("firmware/m33/rtthread.bin"),
        Path("firmware/m33/rtthread.hex"),
        Path("firmware/m33/build/foo.bin"),
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
