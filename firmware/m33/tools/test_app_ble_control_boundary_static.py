from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
M33_DIR = ROOT / "applications" / "m33"
CONTROL_C = ROOT / "applications" / "control" / "control_layer.c"
CONTROL_CFG_H = ROOT / "applications" / "control" / "control_layer_cfg.h"

DIRECT_CONTROL_CALL_RE = re.compile(
    r"\b(?:"
    r"control_motor_[A-Za-z_][A-Za-z0-9_]*|"
    r"control_joint_motor_[A-Za-z_][A-Za-z0-9_]*|"
    r"ctrl_cansimple_send|"
    r"can_send_joint_target|"
    r"ifx_can_direct_send|"
    r"Cy_CANFD_TransmitTxBuffer|"
    r"Cy_CANFD_UpdateAndTransmitMsgBuffer"
    r")\s*(?=\()"
)
ROS_COMMAND_ID_RE = re.compile(r"\bCONTROL_CAN_ID_ROS_COMMAND\b")
ROS_COMMAND_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])0[xX]0*320(?:[uUlL]+)?(?![A-Za-z0-9_])"
)


def is_ble_boundary_source(path):
    if path.suffix.lower() not in {".c", ".h"}:
        return False

    try:
        relative_path = path.relative_to(M33_DIR)
    except ValueError:
        relative_path = path
    return any(
        "ble" in part.lower() or "bt_app" in part.lower()
        for part in relative_path.parts
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


def function_bodies(cleaned_source):
    bodies = []
    index = 0
    while index < len(cleaned_source):
        opening = cleaned_source.find("{", index)
        if opening < 0:
            break
        closing = matching_delimiter(cleaned_source, opening, "{", "}")
        if cleaned_source[:opening].rstrip().endswith(")"):
            bodies.append(cleaned_source[opening + 1 : closing])
        index = closing + 1
    return bodies


def named_function_body(cleaned_source, function_name):
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
            return cleaned_source[opening_brace + 1 : closing_brace]
    raise AssertionError(f"function definition not found: {function_name}")


def find_forbidden_controls(source):
    cleaned_source = strip_c_noncode(source)
    executable_source = "\n".join(function_bodies(cleaned_source))
    offenses = [match.group(0) for match in DIRECT_CONTROL_CALL_RE.finditer(executable_source)]
    offenses.extend(match.group(0) for match in ROS_COMMAND_ID_RE.finditer(cleaned_source))
    offenses.extend(match.group(0) for match in ROS_COMMAND_VALUE_RE.finditer(cleaned_source))
    return list(dict.fromkeys(offenses))


def assert_no_forbidden_controls(test_case, path, source):
    offenses = find_forbidden_controls(source)
    test_case.assertEqual(
        offenses,
        [],
        f"{path.as_posix()}: forbidden BLE direct-control tokens: {offenses}",
    )


def ble_source_paths():
    paths = {
        path
        for pattern in ("*.c", "*.h")
        for path in M33_DIR.rglob(pattern)
        if is_ble_boundary_source(path)
    }
    paths.add(M33_DIR / "bt_runtime_gate.c")
    return sorted(paths)


class AppBleControlBoundaryStaticTest(unittest.TestCase):
    def test_nested_ble_directory_is_selected(self):
        fake_source = M33_DIR / "app_ble_worker" / "protocol.c"
        self.assertTrue(is_ble_boundary_source(fake_source))

    def test_c_scanner_ignores_comments_strings_and_top_level_declarations(self):
        source = r'''
// control_motor_comment(); CONTROL_CAN_ID_ROS_COMMAND 0x320
/* control_joint_motor_comment(); Cy_CANFD_UpdateAndTransmitMsgBuffer(); */
const char *message = "ctrl_cansimple_send(); 0X00320U";
const char marker = '}';
void control_motor_prototype(void);
rt_err_t can_send_joint_target(joint_id_t joint, float target);
rt_err_t ifx_can_direct_send(const void *msg);
cy_rslt_t Cy_CANFD_TransmitTxBuffer(void *base, unsigned int buffer);
'''
        self.assertEqual(find_forbidden_controls(source), [])

    def test_c_scanner_reports_function_calls_and_raw_can_tokens(self):
        source = """
static void app_ble_worker(void)
{
    control_motor_enable();
    Cy_CANFD_UpdateAndTransmitMsgBuffer();
    ifx_can_direct_send();
    Cy_CANFD_TransmitTxBuffer();
    unsigned int can_id = 0X00320u;
    unsigned int ros_id = CONTROL_CAN_ID_ROS_COMMAND;
}
"""
        path = Path("applications/m33/app_ble_worker/protocol.c")

        with self.assertRaises(AssertionError) as raised:
            assert_no_forbidden_controls(self, path, source)

        message = str(raised.exception)
        self.assertIn(path.as_posix(), message)
        self.assertIn("control_motor_enable", message)
        self.assertIn("Cy_CANFD_UpdateAndTransmitMsgBuffer", message)
        self.assertIn("ifx_can_direct_send", message)
        self.assertIn("Cy_CANFD_TransmitTxBuffer", message)
        self.assertIn("0X00320u", message)
        self.assertIn("CONTROL_CAN_ID_ROS_COMMAND", message)

    def test_expected_ble_boundary_sources_are_covered(self):
        covered_names = {path.name for path in ble_source_paths()}
        self.assertTrue(
            {"app_ble_service.c", "bt_app_gatt_handler.c", "bt_runtime_gate.c"}
            <= covered_names,
            f"BLE control-boundary coverage is incomplete: {sorted(covered_names)}",
        )

    def test_ble_sources_do_not_bypass_the_safe_control_boundary(self):
        for path in ble_source_paths():
            relative_path = path.relative_to(ROOT)
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=relative_path.as_posix()):
                assert_no_forbidden_controls(self, relative_path, source)

    def test_nanopi_joint_mask_is_forwarded_from_the_ros_command(self):
        control_c = strip_c_noncode(CONTROL_C.read_text(encoding="utf-8"))
        parser_body = named_function_body(control_c, "ctrl_parse_ros_command_can")
        set_mode_start = parser_body.index("case CONTROL_ROS_CMD_OP_SET_MODE:")
        set_mode_end = parser_body.index("case CONTROL_ROS_CMD_OP_SET_ZERO:", set_mode_start)
        set_mode_body = parser_body[set_mode_start:set_mode_end]
        self.assertIn("out->joint_mask = msg->data[3];", set_mode_body)

    def test_ros_command_can_id_remains_0x320(self):
        control_cfg_h = strip_c_noncode(CONTROL_CFG_H.read_text(encoding="utf-8"))
        self.assertRegex(
            control_cfg_h,
            re.compile(
                r"^\s*#define\s+CONTROL_CAN_ID_ROS_COMMAND\s+0x320U\s*$",
                re.MULTILINE,
            ),
        )


if __name__ == "__main__":
    unittest.main()
