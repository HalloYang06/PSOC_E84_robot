import os
import re
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _find_from_ancestor(relative: Path) -> Path:
    for ancestor in (ROOT, *ROOT.parents):
        candidate = ancestor / relative
        if candidate.is_file():
            return candidate
    return ROOT / relative


OFFICIAL_EI_MODEL = _find_from_ancestor(
    Path("repo")
    / "Extract"
    / "Board_Support_Packages"
    / "Infineon"
    / "PSOC_E84-EDGI-TALK"
    / "1.1.0"
    / "projects"
    / "Edgi_Talk_M55_XiaoZhi"
    / "edge-impulse"
    / "tflite-model"
    / "tflite_learn_333519_3.h"
)
SCONS = _find_from_ancestor(
    Path("platform") / "env_released" / "env-new" / ".venv" / "Scripts" / "scons.exe"
)


def _c_array(path: Path, symbol: str) -> bytes:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"\b{re.escape(symbol)}\s*\[.*?\]\s*(?:[^=]*)=\s*\{{(.*?)\}};", text, re.S)
    assert match, f"array {symbol} not found in {path}"
    return bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{1,2})\b", match.group(1)))


class _FlatBuffer:
    def __init__(self, data: bytes):
        self.data = data
        assert data[4:8] == b"TFL3", "not a TFLite FlatBuffer"

    def u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.data, offset)[0]

    def u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def i32(self, offset: int) -> int:
        return struct.unpack_from("<i", self.data, offset)[0]

    def root(self) -> int:
        return self.u32(0)

    def field(self, table: int, index: int) -> int | None:
        vtable = table - self.i32(table)
        entry = vtable + 4 + index * 2
        if entry + 2 > vtable + self.u16(vtable):
            return None
        relative = self.u16(entry)
        return table + relative if relative else None

    def vector_tables(self, field: int) -> list[int]:
        vector = field + self.u32(field)
        count = self.u32(vector)
        slots = vector + 4
        return [slots + i * 4 + self.u32(slots + i * 4) for i in range(count)]

    def string(self, field: int) -> str:
        string = field + self.u32(field)
        size = self.u32(string)
        return self.data[string + 4:string + 4 + size].decode("ascii")


def _custom_ops(model: bytes) -> list[tuple[str, int]]:
    fb = _FlatBuffer(model)
    operator_codes = fb.field(fb.root(), 1)
    assert operator_codes is not None, "model has no operator code vector"
    result = []
    for operator_code in fb.vector_tables(operator_codes):
        custom_code = fb.field(operator_code, 1)
        if custom_code is None:
            continue
        version_field = fb.field(operator_code, 2)
        version = fb.i32(version_field) if version_field is not None else 1
        result.append((fb.string(custom_code), version))
    return result


def test_experimental_npu_is_default_off_and_fail_closed():
    sconstruct = (ROOT / "SConstruct").read_text(encoding="utf-8")
    applications = (ROOT / "applications" / "SConscript").read_text(encoding="utf-8")
    wake_engine = (ROOT / "applications" / "xiaozhi_wake_engine.c").read_text(encoding="utf-8")

    assert "M55_ETHOSU_EXPERIMENTAL" in sconstruct
    assert "os.environ.get('M55_ETHOSU_EXPERIMENTAL', '0')" in sconstruct
    assert "M55 Ethos-U experimental runtime is not implemented" in sconstruct
    assert "os.environ.get('XIAOZHI_WAKE_BACKEND', 'edge_impulse')" in applications
    assert "def find_edge_impulse_root(start_dir):" in applications
    assert "if os.path.isdir(candidate):" in applications
    assert "M55_ETHOSU_EXPERIMENTAL" not in applications
    assert "if (item == 'ifx_deepcraft') and (not deepcraft_enabled):" in applications
    assert "__has_include" not in wake_engine
    assert not re.search(r"Glob\([^\n]*(?:tensorflow|ethosu)", applications, re.I)
    link_settings = [
        line
        for line in (sconstruct + applications).splitlines()
        if re.search(r"\b(?:LIBS|LIBPATH)\b", line)
    ]
    assert all(not re.search(r"official|edge.impulse|ethos|u55", line, re.I) for line in link_settings)

    assert SCONS.is_file(), f"SCons not found: {SCONS}"
    env = os.environ.copy()
    env["M55_ETHOSU_EXPERIMENTAL"] = "1"
    completed = subprocess.run(
        [str(SCONS), "-n"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "M55 Ethos-U experimental runtime is not implemented" in output


def test_cpu_models_do_not_contain_ethosu_custom_operator():
    official_model = _c_array(OFFICIAL_EI_MODEL, "tflite_learn_333519_3")
    intent_model = _c_array(ROOT / "applications" / "intent_model_int8.cc", "g_intent_model_int8_tflite")

    assert all(name.lower() != "ethos-u" for name, _ in _custom_ops(official_model))
    assert all(name.lower() != "ethos-u" for name, _ in _custom_ops(intent_model))


def test_am_lstm_is_the_only_verified_vela_npu_artifact():
    model_path = ROOT / "applications" / "ifx_deepcraft" / "models" / "AM_LSTM_tflm_model_int16x8.c"
    source = model_path.read_text(encoding="utf-8")
    model = _c_array(model_path, "AM_LSTM_model_bin")

    assert _custom_ops(model).count(("ethos-u", 1)) == 1
    assert [entry for entry in _custom_ops(model) if entry[0].lower() == "ethos-u"] == [("ethos-u", 1)]
    assert "ethos-u-vela 3.11.0" in source


def test_current_rtthread_tflm_ethosu_registration_is_a_stub():
    source = (
        ROOT
        / "packages"
        / "TensorflowLiteMicro-latest"
        / "tensorflow"
        / "lite"
        / "micro"
        / "kernels"
        / "ethosu.cc"
    ).read_text(encoding="utf-8")

    assert re.search(r"Register_ETHOSU\s*\(\s*\)\s*\{\s*return\s+nullptr\s*;\s*\}", source, re.S)
