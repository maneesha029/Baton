"""GitHub REST connector (read-only, user-authorised). Produces the same JSON shape the parsers accept."""
import json
import re

import httpx

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, msg, status=502):
        super().__init__(msg)
        self.status = status


def parse_repo(ref: str):
    ref = ref.strip().rstrip("/")
    m = re.search(r"github\.com[/:]([\w.\-]+)/([\w.\-]+?)(?:\.git)?$", ref) or re.fullmatch(r"([\w.\-]+)/([\w.\-]+)", ref)
    if not m:
        raise GitHubError("Use owner/repo or a github.com URL", 400)
    return m.group(1), m.group(2)


def fetch(ref: str, token: str | None = None, limit: int = 60, transport=None):
    """Return (json_text, summary). `transport` lets tests inject httpx.MockTransport."""
    owner, repo = parse_repo(ref)
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "baton-handover"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    out = []
    try:
        with httpx.Client(base_url=API, headers=hdr, timeout=10, transport=transport) as c:
            for path, params in ((f"/repos/{owner}/{repo}/commits", {"per_page": limit}),
                                 (f"/repos/{owner}/{repo}/issues", {"per_page": min(limit, 30), "state": "all"})):
                r = c.get(path, params=params)
                if r.status_code == 404:
                    raise GitHubError(f"{owner}/{repo} not found (private repos need a token)", 404)
                if r.status_code in (401, 403):
                    raise GitHubError("GitHub refused the request (rate limit or bad token)", 403)
                r.raise_for_status()
                out.extend(r.json())
    except httpx.HTTPError as e:
        raise GitHubError(f"Could not reach GitHub: {e.__class__.__name__}") from e
    return json.dumps(out), {"repo": f"{owner}/{repo}", "items": len(out)}
