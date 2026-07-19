import importlib.util
from pathlib import Path


TOOL_PATH = Path(__file__).with_name("audit_lvgl_cjk_manifest.py")
SPEC = importlib.util.spec_from_file_location("audit_lvgl_cjk_manifest", TOOL_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_extract_cjk_sorts_deduplicates_and_ignores_non_cjk():
    text = 'lv_label_set_text(label, "连接A连接，诊断"); // log only 123'

    assert audit.extract_cjk(text) == "接断诊连"


def test_merge_manifest_includes_business_supplement():
    sources = ['return "等待网络";', 'show("网络连接");']

    assert audit.build_manifest(sources, "助力") == "力助待接等络网连"


def test_source_comments_do_not_enter_manifest():
    source = 'lv_label_set_text(label, "连接"); // 日志不要进入字库'

    assert audit.build_manifest([source], "") == "接连"


def test_parse_lvgl_cmaps_handles_dense_and_sparse_ranges():
    font_source = r"""
static const uint16_t unicode_list_1[] = { 0x0, 0x2, 0x5 };
static const lv_font_fmt_txt_cmap_t cmaps[] = {
    {
        .range_start = 65, .range_length = 3, .glyph_id_start = 1,
        .unicode_list = NULL, .glyph_id_ofs_list = NULL,
        .list_length = 0, .type = LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY
    },
    {
        .range_start = 0x4e00, .range_length = 6, .glyph_id_start = 4,
        .unicode_list = unicode_list_1, .glyph_id_ofs_list = NULL,
        .list_length = 3, .type = LV_FONT_FMT_TXT_CMAP_SPARSE_TINY
    }
};
"""

    coverage = audit.parse_lvgl_font_coverage(font_source)

    assert {65, 66, 67, 0x4E00, 0x4E02, 0x4E05} <= coverage
    assert 0x4E01 not in coverage


def test_known_missing_character_is_reported():
    fixed_ui = "连接康复"
    primary = set(map(ord, "连接"))
    fallback = set(map(ord, "复"))

    assert audit.missing_characters(fixed_ui, primary | fallback) == "康"


def test_check_exit_codes_distinguish_drift_from_missing_coverage():
    assert audit.check_exit_code(drift=True, missing="康") == 2
    assert audit.check_exit_code(drift=False, missing="康") == 3
    assert audit.check_exit_code(drift=False, missing="") == 0


def test_common_font_target_is_exact_gb2312_level1_union_manifest():
    target = audit.common_font_target("康复")

    assert len(target) == 3755
    assert audit.validate_exact_coverage(set(map(ord, target)), target) == (set(), set())

    missing, extra = audit.validate_exact_coverage(
        set(map(ord, target[:-1] + "龘")), target
    )
    assert missing == {ord(target[-1])}
    assert extra == {ord("龘")}


def test_fallback_chain_rejects_wrong_order_and_cycles():
    valid = {
        "rehab_wifi_font": (
            "LV_FONT_DECLARE(rehab_cjk_common_font);\n"
            "const lv_font_t rehab_wifi_font = { .fallback = &rehab_cjk_common_font, };"
        ),
        "rehab_cjk_common_font": (
            "LV_FONT_DECLARE(lv_font_simsun_16_cjk);\n"
            "const lv_font_t rehab_cjk_common_font = { .fallback = &lv_font_simsun_16_cjk, };"
        ),
        "lv_font_simsun_16_cjk": "const lv_font_t lv_font_simsun_16_cjk = { 0 };",
    }

    assert audit.validate_fallback_chain(valid) == audit.EXPECTED_FONT_CHAIN

    wrong = dict(valid)
    wrong["rehab_wifi_font"] = valid["rehab_wifi_font"].replace(
        "rehab_cjk_common_font", "lv_font_simsun_16_cjk"
    )
    cycle = dict(valid)
    cycle["rehab_cjk_common_font"] = valid["rehab_cjk_common_font"].replace(
        "lv_font_simsun_16_cjk", "rehab_wifi_font"
    )
    for sources in (wrong, cycle):
        try:
            audit.validate_fallback_chain(sources)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid fallback chain was accepted")


def test_new_first_party_ui_source_cannot_escape_review(tmp_path):
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "known.c").write_text(
        'lv_label_set_text(label, "已审阅");', encoding="utf-8"
    )
    (applications / "new_ui.cpp").write_text(
        'lv_label_set_text(label, "新增界面");', encoding="utf-8"
    )
    (applications / "log_only.c").write_text(
        'rt_kprintf("诊断日志");', encoding="utf-8"
    )

    discovered, scanned = audit.discover_display_sources(tmp_path)
    unreviewed = audit.unreviewed_display_sources(
        discovered, (Path("applications/known.c"),)
    )

    assert scanned == 3
    assert unreviewed == {Path("applications/new_ui.cpp")}


def test_checked_in_common_cmap_and_fallback_chain_are_exact():
    root = Path(__file__).resolve().parents[1]
    manifest = (root / audit.MANIFEST_PATH).read_text(encoding="utf-8").strip()
    common_source = (root / audit.COMMON_FONT_PATH).read_text(encoding="utf-8")
    common_coverage = audit.parse_lvgl_font_coverage(common_source)
    missing, extra = audit.validate_exact_coverage(
        common_coverage, audit.common_font_target(manifest)
    )
    sources = {
        "rehab_wifi_font": (root / audit.PRIMARY_FONT_PATH).read_text(encoding="utf-8"),
        "rehab_cjk_common_font": common_source,
        "lv_font_simsun_16_cjk": (root / audit.SIMSUN_FONT_PATH).read_text(
            encoding="utf-8"
        ),
    }

    assert missing == set()
    assert extra == set()
    assert audit.validate_fallback_chain(sources) == audit.EXPECTED_FONT_CHAIN
    assert audit.check_exit_code(False, "", audit_errors=True) == 4
