from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "applications/control/rehab_service.c"


def function_body(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def require_guard_before_prepare(body, source_name):
    guard = body.find("rehab_service_validate_assist_position_mask(")
    prepare = body.find("rehab_service_prepare_current_mask(")
    if guard < 0:
        raise AssertionError(f"{source_name} missing assist pre-entry position guard")
    if prepare < 0:
        raise AssertionError(f"{source_name} missing current-mode preparation")
    if guard > prepare:
        raise AssertionError(f"{source_name} validates position after current-mode preparation")


def main():
    source = SOURCE.read_text(encoding="utf-8")
    require_guard_before_prepare(
        function_body(source, "static rt_err_t rehab_service_enter_mode_on_m33("),
        "rehab_service_enter_mode_on_m33",
    )
    require_guard_before_prepare(
        function_body(source, "static rt_err_t rehab_service_set_mode_mask_internal("),
        "rehab_service_set_mode_mask_internal",
    )
    print("rehab assist pre-entry guard static tests passed")


if __name__ == "__main__":
    main()
