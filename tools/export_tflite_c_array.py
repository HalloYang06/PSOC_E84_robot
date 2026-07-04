import argparse
import re
from pathlib import Path


def make_c_symbol(path: Path) -> str:
    stem = re.sub(r"[^0-9a-zA-Z_]", "_", path.stem)
    if stem and stem[0].isdigit():
        stem = f"model_{stem}"
    return f"{stem}_tflite"


def format_c_array(data: bytes, symbol: str, source_name: str) -> str:
    lines = [
        "// Generated from " + source_name,
        '#include <cstdint>',
        "",
        f"alignas(16) extern const unsigned char {symbol}[] = {{",
    ]
    for start in range(0, len(data), 12):
        chunk = data[start : start + 12]
        lines.append("    " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines.extend(
        [
            "};",
            f"extern const unsigned int {symbol}_len = {len(data)};",
            "",
        ]
    )
    return "\n".join(lines)


def export_c_array(input_path: Path, output_path: Path, symbol: str | None = None) -> Path:
    symbol = symbol or make_c_symbol(input_path)
    data = input_path.read_bytes()
    output = format_c_array(data=data, symbol=symbol, source_name=input_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8", newline="\n")
    print(f"[c-array] input={input_path} bytes={len(data)}")
    print(f"[c-array] output={output_path} symbol={symbol}")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a TFLite model as a C array for TFLite Micro.")
    parser.add_argument("--input", required=True, help="Input .tflite path.")
    parser.add_argument("--output", required=True, help="Output .cc path.")
    parser.add_argument("--symbol", default=None, help="C symbol name. Defaults to sanitized file stem + _tflite.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    export_c_array(Path(args.input), Path(args.output), args.symbol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
