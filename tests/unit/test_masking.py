"""PII masking for audit logs and traces."""

import pytest

from mcp_servers.common.masking import mask, mask_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("mail a.b+c@example.co.uk now", "mail [EMAIL] now"),
        ("call +44 7700 900123.", "call [PHONE]."),
        ("call (555) 010-9999 today", "call [PHONE] today"),
        ("card 4111 1111 1111 1111", "card [CARD]"),
        ("IBAN GB82 WEST 1234 5698 7654 32", "IBAN [IBAN]"),
        ("Authorization: Bearer abcdef123456789", "Authorization: [BEARER]"),
        ("wallet 0x52908400098527886E0F7030069857D2E4169EE7", "wallet [CRYPTO_WALLET]"),
    ],
)
def test_mask_text(raw, expected):
    assert mask_text(raw) == expected


@pytest.mark.parametrize(
    "safe",
    [
        "budget $1500.50",
        "version 3.12.12",
        "rated 4.9/5 by 120 clients",
        "job gs_01234 posted 2026-11-01",
    ],
)
def test_mask_leaves_normal_text_alone(safe):
    assert mask_text(safe) == safe


def test_mask_recurses_and_redacts_secret_keys():
    out = mask({"a": ["x@y.io", {"token": "s3cret", "n": 5}], "api_key": "k"})
    assert out == {"a": ["[EMAIL]", {"token": "[REDACTED]", "n": 5}], "api_key": "[REDACTED]"}


def test_mask_truncates_long_strings():
    assert len(mask("x" * 2000)) <= 501
