"""Deadline parsing from claim text. Heuristic on purpose: it only reads explicit dates."""
import re

MO = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_MD = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", re.I)
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")


def _iso(y, m, d):
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_deadlines(text: str, base: str):
    """Dates mentioned in `text`. Month-day mentions resolve to the first occurrence on/after `base` (YYYY-MM-DD)."""
    out, seen = [], set()
    y0 = int(base[:4]) if base and base[:4].isdigit() else 2026
    for m in _ISO.finditer(text):
        s = m.group(0)
        if s not in seen and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
            seen.add(s)
            out.append(s)
    for m in _MD.finditer(text):
        mo, d = MO[m.group(1).lower()] + 1, int(m.group(2))
        if not 1 <= d <= 31:
            continue
        s = _iso(y0, mo, d)
        if base and s < base:
            s = _iso(y0 + 1, mo, d)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def days_between(a: str, b: str) -> int:
    from datetime import date
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (date(ya, ma, da) - date(yb, mb, db)).days
