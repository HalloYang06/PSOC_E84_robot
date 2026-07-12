import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "platform" / "deploy"


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_deployment_files_do_not_reference_legacy_layout():
    deployment_files = (
        "platform/deploy/docker-compose.yml",
        "platform/deploy/docker-compose.public.yml",
        "platform/deploy/api.Dockerfile",
        "platform/deploy/api.prod.Dockerfile",
        "platform/deploy/web.Dockerfile",
        "platform/deploy/web.prod.Dockerfile",
    )
    content = "\n".join(read(path) for path in deployment_files)

    for legacy_path in ("apps/api", "apps/web", "packages/shared", "infra/"):
        assert legacy_path not in content


def test_compose_builds_and_bind_mounts_use_platform_layout():
    local = read("platform/deploy/docker-compose.yml")
    public = read("platform/deploy/docker-compose.public.yml")

    assert "dockerfile: deploy/api.Dockerfile" in local
    assert "dockerfile: deploy/web.Dockerfile" in local
    assert "- ../api/app:/app/app" in local
    assert "- ../web:/app" in local
    assert "dockerfile: deploy/api.prod.Dockerfile" in public
    assert "dockerfile: deploy/web.prod.Dockerfile" in public
    assert local.count("context: ..") == 2
    assert public.count("context: ..") == 2


def test_custom_next_build_outputs_are_ignored():
    generated_paths = (
        "platform/web/.next-prod/BUILD_ID",
        "platform/web/.next-build-staging-123/package.json",
        "platform/web/.next-build-backup-123/package.json",
        "platform/web/next-env.d.ts",
    )

    for path in generated_paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, path


def test_platform_lockfile_has_only_current_workspace_paths():
    lock = json.loads(read("platform/package-lock.json"))
    packages = lock["packages"]

    assert lock["packages"][""]["workspaces"] == ["web", "shared"]
    assert "web" in packages
    assert "shared" in packages
    assert "apps/web" not in packages
    assert "packages/shared" not in packages


def test_readmes_do_not_reference_missing_helper_scripts():
    readmes = read("apps/mobile/README.md") + read("platform/deploy/README.md")

    for missing_helper in (
        "use-android-build-env.ps1",
        "deploy_public_stack.py",
        "preflight_public_deployment.py",
        "smoke_public_deployment.py",
    ):
        assert missing_helper not in readmes


def test_deployment_readme_references_existing_compose_files():
    readme = read("platform/deploy/README.md")

    for compose_file in (
        "platform/deploy/docker-compose.yml",
        "platform/deploy/docker-compose.public.yml",
    ):
        assert compose_file in readme
        assert (ROOT / compose_file).is_file()
