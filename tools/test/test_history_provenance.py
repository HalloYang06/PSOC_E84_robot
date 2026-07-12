import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAP = ROOT / "docs/migration/source-map.json"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
GITHUB_URL_PATTERN = re.compile(r"https://github\.com/[^/]+/[^/]+")


EXPECTED_COMPONENTS = {
    "m33": {
        "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
        "source_ref": "M33",
        "source_commit": "24bae363c50a221dbbaf61c041dfa501a9e539b4",
        "integration_commit": "dc68d812d07eaafcd73f51e5253c688e3914825c",
        "integration_subject": "merge: import M33 firmware history",
        "target_paths": ["firmware/m33"],
    },
    "m55": {
        "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
        "source_ref": "M55",
        "source_commit": "7298c28e81b43fdb5b37e84408cfc62895eaea85",
        "integration_commit": "85ea91c72e2e058ea9f53e149bfc91cb21d49799",
        "integration_subject": "merge: import M55 firmware history",
        "target_paths": ["firmware/m55"],
    },
    "c8t6": {
        "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
        "source_ref": "C8T6",
        "source_commit": "28b79a09dd4813fb31cc776f402183a75ed0e153",
        "integration_commit": "14b4ee0c4edaaf13edb00c23de4f5410d3c9e384",
        "integration_subject": "merge: import C8T6 sensor firmware history",
        "target_paths": ["firmware/c8t6"],
    },
    "ros": {
        "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
        "source_ref": "feature/rehab-arm-ros2-architecture",
        "source_commit": "69450f7165e608f99fc4b574beffa5ac50d2331f",
        "integration_commit": "440efc9c87577d662f4ae6abe3413a50e8f1692f",
        "integration_subject": "merge: import formal ROS2 workspace history",
        "target_paths": ["ros/rehab_arm_ws"],
    },
    "rehab-platform": {
        "source_repository": "https://github.com/wenjunyong666/ai-",
        "source_ref": "app/rehab-arm-mobile-stitch",
        "source_commit": "f6c2c026ce6acda074608aa3e3ada880d62c62d3",
        "integration_commit": "48c5dbd5b47e4c37206980906000a79a1fe9b890",
        "integration_subject": "merge: import rehabilitation app and platform history",
        "target_paths": ["apps/mobile", "platform"],
    },
    "vla": {
        "source_repository": "https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
        "source_ref": "ai",
        "source_commit": "517df8f37105f659f2fe3561b46540ced830c731",
        "integration_commit": "c5d41d5ea4d7d194615fbc49e21edc840710c6cc",
        "integration_subject": "merge: import VLA prototype history",
        "target_paths": ["ai/vla"],
    },
}

EXPECTED_SOURCE_PATHS = {
    "m33": {(".", "firmware/m33")},
    "m55": {(".", "firmware/m55")},
    "c8t6": {(".", "firmware/c8t6")},
    "ros": {("rehab_arm_ros2_ws", "ros/rehab_arm_ws")},
    "rehab-platform": {
        ("apps/mobile/rehab-arm-android", "apps/mobile"),
        ("apps/web", "platform/web"),
        ("apps/api", "platform/api"),
        ("apps/runner", "platform/runner"),
        ("packages/shared", "platform/shared"),
        ("infra", "platform/deploy"),
        ("package.json", "platform/package.json"),
        ("package-lock.json", "platform/package-lock.json"),
    },
    "vla": {("vla_system", "ai/vla")},
}


def git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def source_map():
    return json.loads(SOURCE_MAP.read_text(encoding="utf-8"))


def test_source_map_records_expected_components_and_targets():
    document = source_map()

    assert document["schema_version"] == 1
    assert document["target_repository"] == (
        "https://github.com/HalloYang06/PSOC_E84_robot"
    )
    assert document["target_branch"] == "main"

    components = document["components"]
    names = [component["name"] for component in components]
    paths = [path for component in components for path in component["target_paths"]]

    assert len(names) == len(set(names))
    assert len(paths) == len(set(paths))
    assert set(names) == set(EXPECTED_COMPONENTS)

    for component in components:
        expected = EXPECTED_COMPONENTS[component["name"]]
        assert GITHUB_URL_PATTERN.fullmatch(component["source_repository"])
        for field in (
            "source_repository",
            "source_ref",
            "source_commit",
            "integration_commit",
            "integration_subject",
            "target_paths",
        ):
            assert component[field] == expected[field]
        for path in component["target_paths"]:
            assert (ROOT / path).exists(), path


def test_source_paths_are_complete_and_target_the_component_roots():
    for component in source_map()["components"]:
        mappings = component["source_paths"]
        actual = {(mapping["source"], mapping["target"]) for mapping in mappings}

        assert actual == EXPECTED_SOURCE_PATHS[component["name"]]
        assert all(mapping["source"] and mapping["target"] for mapping in mappings)
        assert all(
            any(
                mapping["target"] == root
                or mapping["target"].startswith(f"{root}/")
                for root in component["target_paths"]
            )
            for mapping in mappings
        )


def test_rehab_platform_exclusions_identify_static_game_assets_and_apks():
    component = next(
        component
        for component in source_map()["components"]
        if component["name"] == "rehab-platform"
    )
    exclusions = " ".join(component["exclusions"]).casefold()

    assert "harvest moon" in exclusions or "farm game" in exclusions
    assert "2d-upgrade" in exclusions
    assert "lib/game" in exclusions
    assert "apk" in exclusions


def test_source_and_integration_commits_preserve_merge_topology():
    for component in source_map()["components"]:
        source = component["source_commit"]
        integration = component["integration_commit"]

        assert SHA_PATTERN.fullmatch(source)
        assert SHA_PATTERN.fullmatch(integration)

        for commit in (source, integration):
            object_type = git("cat-file", "-t", commit)
            assert object_type.returncode == 0, object_type.stderr
            assert object_type.stdout.strip() == "commit"

            ancestor = git("merge-base", "--is-ancestor", commit, "HEAD")
            assert ancestor.returncode == 0, commit

        second_parent = git("rev-parse", f"{integration}^2")
        assert second_parent.returncode == 0, second_parent.stderr
        assert second_parent.stdout.strip() == source

        subject = git("show", "-s", "--format=%s", integration)
        assert subject.returncode == 0, subject.stderr
        assert subject.stdout.strip() == component["integration_subject"]
