"""Source parsers. Every source is normalised to canonical evidence lines:

    [YYYY-MM-DD] @author: body        (author and date optional)

Citations point at (source id, line index) in this canonical text, so what the reviewer reads in the
inspector is exactly what the extractor saw.
"""
import json
import re
from datetime import datetime, timezone

LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]\s*(?:@([\w.\-]+):\s*)?(.*)$")
KINDS = ("git", "notes", "tasks", "chat", "doc", "text")


def parse_line(s: str) -> dict:
    m = LINE_RE.match(s)
    if m:
        return {"date": m.group(1), "author": (m.group(2) or "").lower(), "body": m.group(3).strip()}
    m2 = re.match(r"^@([\w.\-]+):\s*(.*)$", s)
    if m2:
        return {"date": "", "author": m2.group(1).lower(), "body": m2.group(2).strip()}
    return {"date": "", "author": "", "body": s.strip()}


def _date(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{9,}(\.\d+)?", str(v)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).strftime("%Y-%m-%d")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else ""


def _line(date, author, body):
    body = re.sub(r"\s+", " ", str(body)).strip()
    if not body:
        return None
    return f"[{date}] " + (f"@{author}: " if author else "") + body if date else (f"@{author}: " if author else "") + body


def _unwrap(data):
    if isinstance(data, dict):
        for k in ("tasks", "cards", "items", "messages", "commits", "issues", "data"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return data if isinstance(data, list) else []


def detect_kind(name: str, text: str) -> str:
    n = name.lower()
    if n.endswith(".json"):
        try:
            items = _unwrap(json.loads(text))
        except Exception:
            return "text"
        first = next((i for i in items if isinstance(i, dict)), {})
        if "sha" in first or "commit" in first or ("number" in first and "title" in first and "state" in first):
            return "git"
        if "text" in first and any(k in first for k in ("user", "ts", "author", "user_name")):
            return "chat"
        if "title" in first or "status" in first:
            return "tasks"
        return "text"
    if n.endswith((".md", ".markdown")):
        return "doc" if "readme" in n else "notes"
    if n.endswith(".log") or "commit" in n:
        return "git"
    return "text"


def _git_json(items):
    out = []
    for it in items:
        if "commit" in it:  # GitHub commits API
            c = it["commit"]
            who = ((it.get("author") or {}).get("login") or (c.get("author") or {}).get("name") or "").split()[0:1]
            who = (who[0] if who else "").lower()
            out.append((_date((c.get("author") or {}).get("date")), who, (c.get("message") or "").splitlines()[0] if c.get("message") else ""))
        elif "number" in it:  # issues / PRs
            who = ((it.get("user") or {}).get("login") or "").lower()
            tag = "PR" if "pull_request" in it else "issue"
            out.append((_date(it.get("updated_at") or it.get("created_at")), who, f"{tag} #{it['number']} {it.get('title', '')} ({it.get('state', '')})"))
    out.sort(key=lambda r: r[0])
    return [_line(*r) for r in out]


def _tasks(items):
    rows = []
    for t in items:
        if not isinstance(t, dict):
            continue
        tid = t.get("id") or t.get("key") or ""
        title = t.get("title") or t.get("name") or ""
        owner = t.get("owner") or t.get("assignee")
        if isinstance(owner, dict):
            owner = owner.get("name")
        parts = [f"{tid} {title}".strip(), f"owner: {owner if owner else 'unassigned'}"]
        if t.get("status"):
            parts.append(f"status: {t['status']}")
        blk = t.get("blocked_by") or t.get("waiting_on")
        if blk:
            parts.append(f"waiting on {blk}")
        if t.get("due"):
            parts.append(f"due {t['due']}")
        rows.append((_date(t.get("updated") or t.get("updated_at") or t.get("created")), " | ".join(parts)))
    rows.sort(key=lambda r: r[0])
    return [_line(d, "", b) for d, b in rows]


def _chat(items):
    rows = []
    for m in items:
        if not isinstance(m, dict):
            continue
        who = str(m.get("user_name") or m.get("author") or m.get("user") or "").lower().split("@")[0]
        rows.append((_date(m.get("ts") or m.get("date") or m.get("time")), who, m.get("text", "")))
    rows.sort(key=lambda r: r[0])
    return [_line(*r) for r in rows]


def _notes(text):
    cur, fence, out = "", False, []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            fence = not fence
            continue
        if fence or not s:
            continue
        if re.match(r"^#{1,6}\s", s):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
            if m:
                cur = m.group(1)
            continue
        s = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", s)
        s = re.sub(r"\*\*|__|`", "", s)
        out.append(_line(cur, "", s) if cur else s)
    return out


def normalise(name: str, kind: str, text: str) -> list[str]:
    """Return canonical evidence lines for a raw upload. Raises ValueError on unusable input."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    lines = None
    if kind in ("git", "tasks", "chat") and (name.lower().endswith(".json") or text.lstrip().startswith(("[", "{"))):
        try:
            items = _unwrap(json.loads(text))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON: {e.msg} (line {e.lineno})")
        lines = {"git": _git_json, "tasks": _tasks, "chat": _chat}[kind](items)
    elif kind in ("notes", "doc"):
        lines = _notes(text)
    else:  # plain text / git log text: keep lines, canonicalise the optional [date] prefix
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise ValueError("no usable lines found in this source")
    return lines
