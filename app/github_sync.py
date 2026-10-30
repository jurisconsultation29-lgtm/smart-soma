"""OPTION : synchronisation vers GitHub (désactivée par défaut).
Active uniquement si GITHUB_SYNC=1 + GITHUB_TOKEN + GITHUB_REPO. Envoie : Agent Cards, journal d'audit (métadonnées)
et métriques agrégées. JAMAIS les données métier. Le dépôt DOIT être privé."""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .observability import read_audit

AUDIT_KEYS = {"ts", "event", "corr", "sector", "agent", "status", "version", "active", "prev", "hash"}


def enabled():
    e = os.environ.get
    return e("GITHUB_SYNC") == "1" and bool(e("GITHUB_TOKEN")) and bool(e("GITHUB_REPO"))


def _gh(method, path, body=None):
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "multiagent-secteurs", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def _put(repo, branch, path, text, message):
    st, cur = _gh("GET", f"/repos/{repo}/contents/{path}?ref={branch}")
    body = {"message": message, "branch": branch, "content": base64.b64encode(text.encode()).decode()}
    if st == 200 and cur:
        body["sha"] = cur["sha"]
    st, res = _gh("PUT", f"/repos/{repo}/contents/{path}", body)
    if st not in (200, 201):
        raise RuntimeError(f"GitHub HTTP {st}")
    return res["commit"]["sha"]


def push(cards, stats):
    """Pousse gouvernance + audit du jour + métriques agrégées. Retourne {chemin: sha de commit}."""
    if not enabled():
        raise PermissionError("Option GitHub désactivée (GITHUB_SYNC=1, GITHUB_TOKEN, GITHUB_REPO).")
    repo, branch = os.environ["GITHUB_REPO"], os.environ.get("GITHUB_BRANCH", "main")
    st, info = _gh("GET", f"/repos/{repo}")
    if st != 200 or not info.get("private"):
        raise PermissionError("Le dépôt GitHub doit exister et être PRIVÉ.")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = [e for e in read_audit() if e["ts"].startswith(day)]
    if any(set(e) - AUDIT_KEYS for e in rows):
        raise ValueError("Journal d'audit refusé : champ inattendu (protection des données).")
    files = {f"agent_cards/{c['id']}.json": json.dumps(c, ensure_ascii=False, indent=2) for c in cards}
    files[f"audit/{day}.jsonl"] = "\n".join(json.dumps(e, ensure_ascii=False) for e in rows) + "\n"
    files[f"metrics/{day}.json"] = json.dumps({k: v for k, v in stats.items() if k != "alertes"}, ensure_ascii=False, indent=2)
    return {p: _put(repo, branch, p, t, f"sync {p}") for p, t in files.items()}
