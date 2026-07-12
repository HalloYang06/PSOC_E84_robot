"""Audit every unique blob reachable from a Git revision without printing secrets."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import re
import subprocess
from dataclasses import dataclass


MIB = 1024 * 1024
SECRET_PATTERNS = {
    "aws-access-key": re.compile(
        rb"(?<![0-9A-Z])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"
    ),
    # GitHub's classic prefixes use a 36-character alphanumeric suffix.
    "github-token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,255}"),
    "github-fine-grained-token": re.compile(
        rb"github_pat_[A-Za-z0-9_]{60,255}"
    ),
    "openai-key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "private-key-header": re.compile(
        rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
    ),
    "private-key-block": re.compile(
        rb"-----BEGIN (?P<key_type>"
        rb"(?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?"
        rb")PRIVATE KEY-----[\r\n]+"
        rb"[A-Za-z0-9+/=\r\n]{64,}"
        rb"-----END (?P=key_type)PRIVATE KEY-----"
    ),
    "api-key-assignment": re.compile(
        rb"(?i)\bapi[_-]?key\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"
    ),
}
HIGH_CONFIDENCE_PATTERNS = (
    "aws-access-key",
    "github-token",
    "github-fine-grained-token",
    "private-key-block",
)
PLACEHOLDER_MARKERS = (
    b"test",
    b"example",
    b"dummy",
    b"placeholder",
    b"redacted",
    b"never-return",
    b"your_",
    b"undefined",
)


@dataclass(frozen=True)
class Blob:
    oid: str
    size: int
    path: str


def git_output(*args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    ).stdout


def reachable_blobs(revision: str) -> list[Blob]:
    object_paths: dict[str, str] = {}
    for line in git_output("rev-list", "--objects", revision).splitlines():
        oid, separator, path = line.partition(" ")
        object_paths.setdefault(oid, path if separator else "<no-path>")

    object_ids = list(object_paths)
    metadata = git_output(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_text="\n".join(object_ids) + "\n",
    )
    blobs = []
    for line in metadata.splitlines():
        oid, object_type, size_text = line.split()
        if object_type == "blob":
            blobs.append(Blob(oid, int(size_text), object_paths[oid]))
    return blobs


def gate_failure_reasons(
    blobs_at_least_100_mib: int, pattern_matches: dict[str, int]
) -> list[str]:
    reasons = []
    if blobs_at_least_100_mib:
        reasons.append("blob-at-least-100-mib")
    reasons.extend(
        name for name in HIGH_CONFIDENCE_PATTERNS if pattern_matches.get(name, 0)
    )
    return reasons


def audit_exit_code(reasons: list[str], report_only: bool) -> int:
    return 0 if report_only or not reasons else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", nargs="?", default="HEAD")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="report high-confidence findings without failing the process",
    )
    args = parser.parse_args()

    blobs = reachable_blobs(args.revision)
    large = [blob for blob in blobs if blob.size > 20 * MIB]
    limit = [blob for blob in blobs if blob.size >= 100 * MIB]
    candidates: list[tuple[str, Blob, int, int, str]] = []
    api_assignment_literals = 0
    api_assignment_placeholder_literals = 0
    with subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as cat_file:
        assert cat_file.stdin is not None
        assert cat_file.stdout is not None
        for blob in blobs:
            cat_file.stdin.write(f"{blob.oid}\n".encode("ascii"))
            cat_file.stdin.flush()
            header = cat_file.stdout.readline().decode("ascii").split()
            if len(header) != 3 or header[1] != "blob":
                raise RuntimeError(f"Unexpected cat-file response for {blob.oid}")
            content = cat_file.stdout.read(int(header[2]))
            if cat_file.stdout.read(1) != b"\n":
                raise RuntimeError(f"Missing cat-file delimiter for {blob.oid}")
            for name, pattern in SECRET_PATTERNS.items():
                matches = [match.group(0) for match in pattern.finditer(content)]
                if matches:
                    placeholder_count = sum(
                        any(marker in match.lower() for marker in PLACEHOLDER_MARKERS)
                        for match in matches
                    )
                    fingerprints = ",".join(
                        hashlib.sha256(match).hexdigest()[:12] for match in matches
                    )
                    candidates.append(
                        (name, blob, len(matches), placeholder_count, fingerprints)
                    )
                    if name == "api-key-assignment":
                        for match in matches:
                            value = re.split(rb"[:=]", match, maxsplit=1)[1].lstrip()
                            if value[:1] in (b"'", b'"'):
                                api_assignment_literals += 1
                                if any(
                                    marker in value.lower()
                                    for marker in PLACEHOLDER_MARKERS
                                ):
                                    api_assignment_placeholder_literals += 1

    print(f"revision={args.revision}")
    print(f"unique_blobs={len(blobs)}")
    print(f"blobs_over_20_mib={len(large)}")
    for blob in large:
        print(f"large oid={blob.oid} size={blob.size} path={blob.path}")
    print(f"blobs_at_least_100_mib={len(limit)}")
    print(f"secret_pattern_candidates={len(candidates)}")
    candidate_blobs = Counter(name for name, *_ in candidates)
    candidate_matches = {
        name: sum(
            count for item_name, _, count, _, _ in candidates if item_name == name
        )
        for name in SECRET_PATTERNS
    }
    for name in SECRET_PATTERNS:
        print(
            f"pattern_summary pattern={name} "
            f"blobs={candidate_blobs[name]} matches={candidate_matches[name]}"
        )
    print(f"api_assignment_literal_matches={api_assignment_literals}")
    print(
        "api_assignment_placeholder_literals="
        f"{api_assignment_placeholder_literals}"
    )
    gate_reasons = gate_failure_reasons(len(limit), candidate_matches)
    print(f"mode={'report-only' if args.report_only else 'gate'}")
    print(f"gate_failures={','.join(gate_reasons) if gate_reasons else 'none'}")
    for name, blob, match_count, placeholder_count, fingerprints in candidates:
        print(
            f"candidate pattern={name} oid={blob.oid} "
            f"size={blob.size} matches={match_count} "
            f"placeholder_marked={placeholder_count} "
            f"fingerprints={fingerprints} path={blob.path}"
        )
    return audit_exit_code(gate_reasons, args.report_only)


if __name__ == "__main__":
    raise SystemExit(main())
