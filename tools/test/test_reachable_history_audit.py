import pytest

from tools import audit_reachable_history as audit


SECRET_PATTERNS = audit.SECRET_PATTERNS


def gate_failure_reasons(*args, **kwargs):
    gate = getattr(audit, "gate_failure_reasons", None)
    assert gate is not None, "gate_failure_reasons must implement gate-mode failures"
    return gate(*args, **kwargs)


@pytest.mark.parametrize(
    ("pattern_name", "sample"),
    [
        ("aws-access-key", b"AK" + b"IA1234567890ABCDEF"),
        ("aws-access-key", b"AS" + b"IA1234567890ABCDEF"),
        ("github-token", b"ghp_" + b"A1" * 18),
        ("github-fine-grained-token", b"github_pat_" + b"A1_" * 20),
    ],
)
def test_high_confidence_token_patterns_cover_supported_formats(
    pattern_name: str, sample: bytes
) -> None:
    assert SECRET_PATTERNS[pattern_name].search(sample)


@pytest.mark.parametrize("key_type", [b"DSA ", b"ENCRYPTED "])
def test_private_key_patterns_cover_additional_pem_types(key_type: bytes) -> None:
    sample = (
        b"-----BEGIN "
        + key_type
        + b"PRIVATE KEY-----\n"
        + b"QUFB" * 20
        + b"\n-----END "
        + key_type
        + b"PRIVATE KEY-----"
    )

    assert SECRET_PATTERNS["private-key-header"].search(sample)
    assert SECRET_PATTERNS["private-key-block"].search(sample)


def test_gate_rejects_each_high_confidence_finding() -> None:
    assert gate_failure_reasons(1, {}) == ["blob-at-least-100-mib"]
    assert gate_failure_reasons(0, {"aws-access-key": 1}) == ["aws-access-key"]
    assert gate_failure_reasons(0, {"github-token": 1}) == ["github-token"]
    assert gate_failure_reasons(0, {"github-fine-grained-token": 1}) == [
        "github-fine-grained-token"
    ]
    assert gate_failure_reasons(0, {"private-key-block": 1}) == [
        "private-key-block"
    ]


def test_gate_allows_report_only_candidates() -> None:
    assert gate_failure_reasons(
        0,
        {
            "openai-key": 2,
            "private-key-header": 3,
            "api-key-assignment": 4,
        },
    ) == []


def test_report_only_must_be_explicit_to_suppress_gate_failure() -> None:
    exit_code = getattr(audit, "audit_exit_code", None)
    assert exit_code is not None, "audit_exit_code must enforce gate mode by default"
    assert exit_code(["aws-access-key"], report_only=False) == 1
    assert exit_code(["aws-access-key"], report_only=True) == 0
    assert exit_code([], report_only=False) == 0
