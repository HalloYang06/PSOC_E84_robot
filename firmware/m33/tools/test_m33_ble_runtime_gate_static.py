from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = ROOT / "applications"
GATE_PATH = APPLICATIONS / "m33" / "bt_runtime_gate.c"
GATE_C = GATE_PATH.read_text(encoding="utf-8")
M33_SCONSCRIPT = (APPLICATIONS / "m33" / "SConscript").read_text(encoding="utf-8")
CALL_RE = re.compile(r"\bm33_ble_gate_start\s*\(\s*\)")
DEFINITION_RE = re.compile(
    r"\bstatic\s+rt_err_t\s+m33_ble_gate_start\s*\(\s*void\s*\)\s*\{"
)


def strip_c_noncode(source):
    result = list(source)
    state = "code"
    i = 0

    while i < len(source):
        char = source[i]
        next_char = source[i + 1] if i + 1 < len(source) else ""

        if state == "code":
            if char == "/" and next_char == "/":
                result[i] = result[i + 1] = " "
                state = "line_comment"
                i += 2
                continue
            if char == "/" and next_char == "*":
                result[i] = result[i + 1] = " "
                state = "block_comment"
                i += 2
                continue
            if char == '"':
                result[i] = " "
                state = "string"
            elif char == "'":
                result[i] = " "
                state = "char"
            i += 1
            continue

        if state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                result[i] = " "
            i += 1
            continue

        if state == "block_comment":
            if char == "*" and next_char == "/":
                result[i] = result[i + 1] = " "
                state = "code"
                i += 2
            else:
                if char != "\n":
                    result[i] = " "
                i += 1
            continue

        quote = '"' if state == "string" else "'"
        if char == "\\" and next_char:
            result[i] = " "
            if next_char != "\n":
                result[i + 1] = " "
            i += 2
        elif char == quote:
            result[i] = " "
            state = "code"
            i += 1
        elif char == "\n":
            state = "code"
            i += 1
        else:
            result[i] = " "
            i += 1

    return "".join(result)


def matching_delimiter(source, opening_index, opening, closing):
    depth = 0
    for index in range(opening_index, len(source)):
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError(f"unmatched {opening!r} at offset {opening_index}")


def named_function_body_span(cleaned_source, function_name):
    name_re = re.compile(rf"\b{re.escape(function_name)}\s*\(")
    for match in name_re.finditer(cleaned_source):
        opening_parenthesis = cleaned_source.find("(", match.start())
        closing_parenthesis = matching_delimiter(
            cleaned_source, opening_parenthesis, "(", ")"
        )
        opening_brace = closing_parenthesis + 1
        while (
            opening_brace < len(cleaned_source)
            and cleaned_source[opening_brace].isspace()
        ):
            opening_brace += 1
        if opening_brace < len(cleaned_source) and cleaned_source[opening_brace] == "{":
            closing_brace = matching_delimiter(cleaned_source, opening_brace, "{", "}")
            return opening_brace + 1, closing_brace
    raise AssertionError(f"function definition not found: {function_name}")


class M33BleRuntimeGateStaticTest(unittest.TestCase):
    def test_call_matcher_ignores_non_code_and_detects_expression_calls(self):
        source = r'''
// m33_ble_gate_start();
/* m33_ble_gate_start() */
const char *message = "m33_ble_gate_start()";
const int marker = 'm33_ble_gate_start()';
if (m33_ble_gate_start()) {}
'''
        matches = list(CALL_RE.finditer(strip_c_noncode(source)))
        self.assertEqual(len(matches), 1)
        self.assertIsNone(CALL_RE.search("static rt_err_t m33_ble_gate_start(void)"))

    def test_runtime_fallback_is_disabled_and_never_auto_started(self):
        self.assertIn("#define M33_ENABLE_APP_BLE_RUNTIME 0", GATE_C)
        self.assertNotIn("INIT_APP_EXPORT", GATE_C)
        self.assertNotIn("INIT_ENV_EXPORT", GATE_C)

    def test_normal_build_includes_runtime_with_explicit_opt_out(self):
        self.assertIn("M33_APP_BLE_RUNTIME", M33_SCONSCRIPT)
        self.assertRegex(
            M33_SCONSCRIPT,
            r"os\.environ\.get\(\s*['\"]M33_APP_BLE_RUNTIME['\"]\s*,\s*['\"]1['\"]\s*\)\s*==\s*['\"]1['\"]",
        )
        self.assertIn("M33_ENABLE_APP_BLE_RUNTIME=1", M33_SCONSCRIPT)
        self.assertRegex(
            M33_SCONSCRIPT,
            r"DefineGroup\([^\n]+CPPDEFINES\s*=\s*cppdefines",
        )

    def test_shell_command_is_the_only_runtime_start_caller(self):
        calls = []
        source_paths = sorted(APPLICATIONS.rglob("*.c")) + sorted(APPLICATIONS.rglob("*.h"))
        for path in source_paths:
            source = strip_c_noncode(path.read_text(encoding="utf-8"))
            for match in CALL_RE.finditer(source):
                calls.append((path.relative_to(ROOT).as_posix(), match.start()))

        self.assertEqual(
            [path for path, _ in calls],
            ["applications/m33/bt_runtime_gate.c"],
            "m33_ble_gate_start() must have exactly one call site in the BLE Shell command",
        )

        cleaned_gate = strip_c_noncode(GATE_C)
        shell_start, shell_end = named_function_body_span(cleaned_gate, "cmd_m33_ble_start")
        self.assertLess(shell_start, calls[0][1])
        self.assertLess(calls[0][1], shell_end)
        self.assertRegex(cleaned_gate, DEFINITION_RE)

    def test_manual_start_is_single_owner_and_ordered(self):
        self.assertIn("M33_BLE_GATE_STARTING", GATE_C)
        self.assertIn("M33_BLE_GATE_FAILED", GATE_C)
        start = GATE_C.index("static rt_err_t m33_ble_gate_start")
        end = GATE_C.index("static int cmd_m33_ble_start", start)
        body = GATE_C[start:end]
        calls = [
            "app_ble_service_init()",
            "app_ble_service_start()",
            "bt_hci_transport_init()",
            "bt_hci_transport_start()",
        ]
        positions = [body.index(call) for call in calls]
        self.assertEqual(positions, sorted(positions))

    def test_shell_exposes_start_and_status_only(self):
        self.assertIn("MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_start", GATE_C)
        self.assertIn("MSH_CMD_EXPORT_ALIAS(cmd_m33_ble_status", GATE_C)
        self.assertNotIn("clear_bonds", GATE_C)
        self.assertNotIn("deinit", GATE_C.lower())


if __name__ == "__main__":
    unittest.main()
