"""PII masking for logs and audit records (emails, phone numbers, payment details, secrets).

Order matters: specific formats (wallets, IBANs, bearer tokens) run before the generic digit
patterns (cards, phones) so a long identifier is masked as one thing, not chopped up.
"""

from __future__ import annotations

import re
from typing import Any

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")),
    (
        "crypto_wallet",
        re.compile(r"\b(?:0x[a-fA-F0-9]{40}|bc1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"),
    ),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")),
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    # phone: 10-15 digits, optional +/( and up to two separators between digits; may end a
    # sentence ("...900123.") but is not part of a decimal or a longer word
    ("phone", re.compile(r"(?<![\w.])\+?\(?(?:\d[\s().-]{0,2}){9,14}\d(?!\w)(?!\.\d)")),
]
SECRET_KEYS = {"token", "authorization", "password", "api_key", "secret", "access_token"}
MAX_STR = 500


def mask_text(text: str) -> str:
    for name, pat in PATTERNS:
        text = pat.sub(f"[{name.upper()}]", text)
    return text


def mask(value: Any, *, truncate: bool = True) -> Any:
    """Recursively mask strings in dicts/lists; drop values of secret-looking keys."""
    if isinstance(value, str):
        out = mask_text(value)
        return out[:MAX_STR] + "…" if truncate and len(out) > MAX_STR else out
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in SECRET_KEYS else mask(v, truncate=truncate)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [mask(v, truncate=truncate) for v in value]
    return value
