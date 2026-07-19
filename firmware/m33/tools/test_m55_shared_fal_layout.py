from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_m55_persistent_partitions_use_independent_erase_sectors() -> None:
    header = (
        ROOT / "libraries" / "Common" / "board" / "ports" / "fal" / "fal_cfg.h"
    ).read_text(encoding="utf-8")

    assert '"filesystem",     NOR_FLASH_DEV_NAME, 0x100000,  512*1024' in header
    assert '"wifi_cfg",       NOR_FLASH_DEV_NAME, 0x180000,  256*1024' in header
    assert '"xiaozhi_cfg",    NOR_FLASH_DEV_NAME, 0x1C0000,  256*1024' in header
    assert '"filesystem",     NOR_FLASH_DEV_NAME, 0x100000, 1024*1024' not in header
