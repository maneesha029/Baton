"""Access levels, roles and secret masking.

Levels order every source and every claim: public < team < confidential.
A claim's level is the MAX level of all sources cited by it, so a claim can never be
more visible than the most restricted text behind it.
"""
import re

LEVELS = {"public": 0, "team": 1, "confidential": 2}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}
ROLES = {"guest": 0, "developer": 1, "manager": 2}

# (pattern, replacement). Secrets are masked irreversibly on ingest, before storage and before any model call.
_SECRET_RULES = [
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\b"), "[SECRET REDACTED]"),
    (re.compile(r"\b(?:sk|key|tok|api)_[A-Za-z0-9_]{8,}\b"), "[SECRET REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[SECRET REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[SECRET REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer [SECRET REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)(\s*[:=]\s*)(?!\[SECRET)\S+"), r"\1\2[SECRET REDACTED]"),
    (re.compile(r"(?<![\w-])(?:\+\d{1,3}[ -]?)?\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?![\w-])"), "[PHONE REDACTED]"),
]


def mask(text: str):
    """Return (masked_text, number_of_redactions)."""
    n = 0
    for rx, rep in _SECRET_RULES:
        text, k = rx.subn(rep, text)
        n += k
    return text, n


def clearance(role: str) -> int:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    return ROLES[role]


def can_see(level: int, role: str) -> bool:
    return level <= clearance(role)
