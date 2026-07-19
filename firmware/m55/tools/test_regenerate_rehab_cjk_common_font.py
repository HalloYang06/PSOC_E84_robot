import importlib.util
from pathlib import Path


TOOL_PATH = Path(__file__).with_name("regenerate_rehab_cjk_common_font.py")
SPEC = importlib.util.spec_from_file_location("regenerate_rehab_cjk_common_font", TOOL_PATH)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)

ROOT = Path(__file__).resolve().parents[1]


def test_gb2312_level1_is_exact_and_contains_fixed_ui_manifest():
    common = generator.gb2312_level1_characters()
    manifest = (ROOT / "docs/LVGL固定界面中文字形清单.txt").read_text(
        encoding="utf-8"
    ).strip()

    assert len(common) == 3755
    assert len(set(common)) == 3755
    assert common == "".join(sorted(common, key=ord))
    assert {"啊", "座"} <= set(common)
    assert set(manifest) <= set(common)


def test_generation_command_pins_18px_2bpp_and_tool_version():
    command = generator.build_command(
        Path("NotoSansSC.otf"), "啊座", Path("rehab_cjk_common_font.c")
    )

    assert command[:4] == ["npx", "--yes", "lv_font_conv@1.5.3", "--font"]
    assert command[command.index("--symbols") + 1] == "啊座"
    assert command[command.index("--size") + 1] == "18"
    assert command[command.index("--bpp") + 1] == "2"
    assert command[command.index("--lv-font-name") + 1] == "rehab_cjk_common_font"
    assert command[command.index("--lv-include") + 1] == "lvgl.h"
    assert "--range" not in command
    assert "--no-compress" in command


def test_generated_common_font_is_const_flash_data_with_simsun_fallback():
    generated = '''#include "lvgl.h"
static const uint8_t glyph_bitmap[] = { 0 };
static const lv_font_fmt_txt_dsc_t font_dsc = { 0 };
const lv_font_t rehab_cjk_common_font = {
#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9
    .fallback = NULL,
#endif
    .user_data = NULL,
};
'''

    patched = generator.patch_simsun_fallback(generated)

    assert "static const uint8_t glyph_bitmap[]" in patched
    assert "static const lv_font_fmt_txt_dsc_t font_dsc" in patched
    assert "const lv_font_t rehab_cjk_common_font" in patched
    assert "LV_FONT_DECLARE(lv_font_simsun_16_cjk);" in patched
    assert ".fallback = &lv_font_simsun_16_cjk," in patched
    assert ".fallback = NULL," not in patched


def test_primary_font_and_lvgl_disabled_build_wiring_reference_common_font():
    primary = (ROOT / "applications/rehab_wifi_font.c").read_text(encoding="utf-8")
    sconscript = (ROOT / "applications/SConscript").read_text(encoding="utf-8")

    assert "LV_FONT_DECLARE(rehab_cjk_common_font);" in primary
    assert ".fallback = &rehab_cjk_common_font," in primary
    assert "'rehab_cjk_common_font.c'" in sconscript


def test_checked_in_common_font_is_const_and_generation_is_reproducible():
    source = (ROOT / "applications/rehab_cjk_common_font.c").read_text(
        encoding="utf-8"
    )

    assert "static LV_ATTRIBUTE_LARGE_CONST const uint8_t glyph_bitmap[]" in source
    assert "const lv_font_t rehab_cjk_common_font" in source
    assert generator.gb2312_level1_characters() == generator.gb2312_level1_characters()
