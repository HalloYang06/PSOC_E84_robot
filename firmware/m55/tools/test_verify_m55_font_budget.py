import importlib.util
import hashlib
from pathlib import Path


TOOL_PATH = Path(__file__).with_name("verify_m55_font_budget.py")
SPEC = importlib.util.spec_from_file_location("verify_m55_font_budget", TOOL_PATH)
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)


def test_parse_size_text_and_load_end_from_allocated_nvm_sections():
    size_output = "text data bss dec hex filename\n2067636 17560 4531780 0 0 rt-thread.elf\n"
    sections = """
  1 .app_code_main 001e4cc8 60580400 60580400 00010400 2**4
                  CONTENTS, ALLOC, LOAD, READONLY, CODE
  6 .data 000012ec 20000000 60779108 00220000 2**2
                  CONTENTS, ALLOC, LOAD, DATA
 14 .heap 0015cea8 26063158 6077d54c 00233158 2**0
                  ALLOC
"""

    assert budget.parse_text_size(size_output) == 2067636
    assert budget.parse_nvm_load_end(sections) == 0x6077A3F4


def test_budget_enforces_delta_and_headroom_limits():
    result = budget.evaluate_budget(
        baseline_text=1_718_900,
        current_text=2_067_636,
        load_end=0x6077D54C,
    )

    assert result["text_delta"] == 348_736
    assert result["headroom"] == 0x60D80000 - 0x6077D54C

    for current_text, load_end in (
        (1_718_900 + budget.MAX_TEXT_DELTA + 1, 0x6077D54C),
        (2_067_636, budget.NVM_LIMIT - budget.MIN_HEADROOM + 1),
    ):
        try:
            budget.evaluate_budget(1_718_900, current_text, load_end)
        except ValueError:
            pass
        else:
            raise AssertionError("font budget violation was accepted")


def test_baseline_binding_requires_documented_commit_and_config_hash(tmp_path):
    config = tmp_path / ".config"
    config.write_bytes(b"CONFIG_TEST=y\n")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    metadata = {
        "baseline_commit": "041f1cb3171827caae1edda44034baa195cea09d",
        "baseline_text": "1718900",
        "config_path": ".config",
        "config_sha256": digest,
    }

    bound, reason = budget.baseline_binding(tmp_path, metadata)
    assert bound is True
    assert reason == "bound"

    config.write_bytes(b"CONFIG_TEST=n\n")
    bound, reason = budget.baseline_binding(tmp_path, metadata)
    assert bound is False
    assert reason == "config_sha256_mismatch"
