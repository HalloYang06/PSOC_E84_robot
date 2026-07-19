import importlib.util
from pathlib import Path


TOOL_PATH = Path(__file__).with_name("regenerate_rehab_wifi_font.py")
SPEC = importlib.util.spec_from_file_location("regenerate_rehab_wifi_font", TOOL_PATH)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_generation_command_pins_font_conv_and_existing_font_options():
    command = generator.build_command(
        Path("NotoSansSC.otf"), "助力", Path("rehab_wifi_font.c")
    )

    assert command[:4] == ["npx", "--yes", "lv_font_conv@1.5.3", "--font"]
    assert command[4] == "NotoSansSC.otf"
    assert command[command.index("--range") + 1] == generator.PRESERVED_RANGE
    assert command[command.index("--symbols") + 1] == "助力"
    assert command[command.index("--size") + 1] == "18"
    assert command[command.index("--bpp") + 1] == "4"
    assert command[command.index("--lv-include") + 1] == "lvgl.h"
    assert "--no-compress" in command


def test_patch_fallback_wires_common_cjk_font():
    generated = '''#ifdef LV_LVGL_H_INCLUDE_SIMPLE
#include "lvgl.h"
#else
#include "lvgl.h"
#endif

const lv_font_t rehab_wifi_font = {
    .dsc = &font_dsc,
#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9
    .fallback = NULL,
#endif
    .user_data = NULL,
};
'''

    patched = generator.patch_common_fallback(generated)

    assert "LV_LVGL_H_INCLUDE_SIMPLE" not in patched
    assert '#include "lvgl.h"\n\nLV_FONT_DECLARE' in patched
    assert "LV_FONT_DECLARE(rehab_cjk_common_font);" in patched
    assert ".fallback = &rehab_cjk_common_font," in patched
    assert ".fallback = NULL," not in patched
    assert patched.count(".fallback =") == 1
    assert patched.count("rehab_cjk_common_font") == 2


def test_manifest_must_be_sorted_unique_cjk():
    generator.validate_manifest("力助")

    for invalid in ("助力", "力力", "力A"):
        try:
            generator.validate_manifest(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid manifest accepted: {invalid}")


def test_generation_preserves_legacy_primary_cjk():
    symbols = generator.generation_symbols("力助")

    assert symbols == "".join(sorted(set(symbols), key=ord))
    assert set(generator.LEGACY_PRIMARY_CJK) <= set(symbols)
    assert {"力", "助"} <= set(symbols)
