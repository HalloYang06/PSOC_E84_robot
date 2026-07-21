from pathlib import Path


CLIENT_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "app"
    / "projects"
    / "[id]"
    / "rehab-arm-control"
    / "rehab-arm-control-client.tsx"
)


def test_camera_preview_refresh_is_decoupled_from_dashboard_polling():
    source = CLIENT_SOURCE.read_text(encoding="utf-8")

    assert "CAMERA_PREVIEW_REFRESH_MS = 350" in source
    assert 'activeModule !== "vision"' in source
    assert 'document.visibilityState === "hidden"' in source
    assert "window.setInterval(refreshPreviewImages, CAMERA_PREVIEW_REFRESH_MS)" in source
    assert "withImageVersion(src, Date.now())" in source
    assert 'img[data-role="${role}"]' in source
    assert "camera/keyframes/stereo_left/latest/file" in source
    assert "camera/keyframes/stereo_right/latest/file" in source
    assert "[activeModule, apiBaseUrl, selected?.device_id]" in source
