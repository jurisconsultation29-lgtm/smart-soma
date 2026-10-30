"""Observabilité : correlation ID, métriques, alertes, audit à chaîne de hachage, kill switch.
Ce module n'a AUCUNE dépendance externe."""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()
CORR_RX = re.compile(r"^[A-Za-z0-9_-]{6,40}$")


def new_corr(prefix="API"):
    """Identifiant de corrélation : présent sur CHAQUE exécution (critère Observabilité)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def clean_corr(value):
    """Accepte un identifiant venant de l'extérieur s'il est sûr, sinon en crée un."""
    return value if value and CORR_RX.match(value) else new_corr()


def data_dir():
    p = Path(os.environ.get("DATA_DIR", "./data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ Métriques et alertes
class Monitor:
    def __init__(self, latency_ms=None):
        self.latency_ms = latency_ms or int(os.environ.get("LATENCY_ALERT_MS", "5000"))
        self.runs = deque(maxlen=500)
        self.alerts = deque(maxlen=100)

    def record(self, agent, sector, status, ms, corr):
        """status : 'succes' | 'refus' (entrée invalide) | 'erreur' (incident)."""
        self.runs.append({"corr": corr, "agent": agent, "sector": sector, "status": status, "ms": ms, "ts": time.time()})
        if status == "erreur" or ms > self.latency_ms:
            self.alerts.append({"corr": corr, "agent": agent, "status": status, "ms": ms, "seuil_ms": self.latency_ms,
                                "action": "Appliquer le runbook : contention, analyse des logs, rollback si besoin."})

    def stats(self):
        runs = list(self.runs)
        ok = [r for r in runs if r["status"] == "succes"]
        err = [r for r in runs if r["status"] == "erreur"]
        by_agent = {}
        for r in runs:
            a = by_agent.setdefault(r["agent"], {"executions": 0, "erreurs": 0})
            a["executions"] += 1
            a["erreurs"] += r["status"] == "erreur"
        return {"executions": len(runs), "succes": len(ok), "erreurs": len(err),
                "taux_erreur": round(len(err) / len(runs), 3) if runs else 0.0,
                "latence_moyenne_ms": int(sum(r["ms"] for r in ok) / len(ok)) if ok else 0,
                "par_agent": by_agent, "alertes": list(self.alerts)[-5:]}


# ------------------------------------------------------------------ Audit à chaîne de hachage
def _h(entry):
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def audit(event, **fields):
    """Journal append-only : chaque entrée contient le hachage de la précédente. Jamais de données métier."""
    with _lock:
        f = data_dir() / "audit.jsonl"
        prev = "0" * 64
        if f.exists() and f.stat().st_size:
            prev = json.loads(f.read_text(encoding="utf-8").strip().splitlines()[-1])["hash"]
        e = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields, "prev": prev}
        e["hash"] = _h(e)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def read_audit():
    f = data_dir() / "audit.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x] if f.exists() else []


def verify_chain():
    prev = "0" * 64
    rows = read_audit()
    for i, e in enumerate(rows):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("prev") != prev or _h(body) != e.get("hash"):
            return {"valid": False, "broken_at": i}
        prev = e["hash"]
    return {"valid": True, "entries": len(rows)}


# ------------------------------------------------------------------ Kill switch
def get_state():
    f = data_dir() / "state.json"
    return json.loads(f.read_text()) if f.exists() else {"kill": False, "reason": "", "since": ""}


def set_state(active, reason=""):
    s = {"kill": bool(active), "reason": reason[:200], "since": datetime.now(timezone.utc).isoformat()}
    (data_dir() / "state.json").write_text(json.dumps(s))
    audit("kill_switch", active=bool(active))
    return s
