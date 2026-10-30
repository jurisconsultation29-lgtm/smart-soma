"""API FastAPI : architecture multi-agents par secteur.
Lancement : uvicorn app.main:app --port 8001      (Render : variable PORT gérée par le Dockerfile)"""
import hmac
import os
from typing import Optional

from fastapi import Body, FastAPI, Header, HTTPException, Request

from . import governance
from .agents import Orchestrator, Suspended, UnknownSector
from .observability import audit, clean_corr, get_state, read_audit, set_state, verify_chain

API_KEY = os.environ.get("AGENT_API_KEY", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
if os.environ.get("ALLOW_INSECURE_DEV") != "1" and (len(API_KEY) < 16 or len(ADMIN_TOKEN) < 16):
    raise RuntimeError("AGENT_API_KEY et ADMIN_TOKEN (16 caractères minimum) sont obligatoires.")

app = FastAPI(title="Multi-agents par secteur", version="1.0.0")
ORCH = Orchestrator()


@app.middleware("http")
async def correlation(request: Request, call_next):
    request.state.corr = clean_corr(request.headers.get("x-correlation-id"))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.corr
    return response


def need(given: Optional[str], expected: str, msg: str):
    if not expected or not hmac.compare_digest(given or "", expected):
        raise HTTPException(401, msg)


@app.get("/health")
def health():
    return {"ok": True, "version": app.version, "kill_switch": get_state()["kill"]}


@app.get("/api/agents")
def agents():
    return [{"id": c["id"], "sector": c["sector"], "version": c["version"]} for c in ORCH.all_cards()]


@app.get("/api/agent-card/{agent_id}")
def agent_card(agent_id: str):
    for c in ORCH.all_cards():
        if c["id"] == agent_id:
            return c
    raise HTTPException(404, "Agent inconnu")


@app.get("/api/governance/check")
def governance_check():
    return [governance.card_status(c) for c in ORCH.all_cards()]


@app.get("/api/runbook")
def runbook():
    return governance.RUNBOOK


@app.post("/api/analyze/{sector}")
def analyze(sector: str, request: Request, payload: dict = Body(...), x_api_key: Optional[str] = Header(None)):
    need(x_api_key, API_KEY, "Clé d'API invalide")
    try:
        return ORCH.run(sector, payload, request.state.corr)
    except UnknownSector:
        raise HTTPException(404, "Secteur inconnu")
    except Suspended:
        raise HTTPException(503, "Agent suspendu (kill switch actif)")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/monitoring")
def monitoring(x_admin_token: Optional[str] = Header(None)):
    need(x_admin_token, ADMIN_TOKEN, "Jeton d'administration invalide")
    return ORCH.monitoring.check(ORCH.monitor)


@app.get("/api/audit")
def get_audit(limit: int = 100, x_admin_token: Optional[str] = Header(None)):
    need(x_admin_token, ADMIN_TOKEN, "Jeton d'administration invalide")
    return read_audit()[-max(1, min(limit, 1000)):]


@app.get("/api/audit/verify")
def audit_verify(x_admin_token: Optional[str] = Header(None)):
    need(x_admin_token, ADMIN_TOKEN, "Jeton d'administration invalide")
    return verify_chain()


@app.post("/api/admin/kill-switch")
def kill_switch(body: dict = Body(...), x_admin_token: Optional[str] = Header(None)):
    need(x_admin_token, ADMIN_TOKEN, "Jeton d'administration invalide")
    return set_state(bool(body.get("active")), str(body.get("reason", "")))


@app.post("/api/admin/github/sync")
def github_sync(x_admin_token: Optional[str] = Header(None)):
    """OPTION : désactivée tant que GITHUB_SYNC=1 n'est pas défini."""
    need(x_admin_token, ADMIN_TOKEN, "Jeton d'administration invalide")
    from . import github_sync as gs                      # import tardif : l'option reste facultative
    if not gs.enabled():
        raise HTTPException(501, "Option GitHub désactivée")
    try:
        commits = gs.push(ORCH.all_cards(), ORCH.monitor.stats())
    except (PermissionError, ValueError, RuntimeError) as e:
        audit("github.sync.echec", erreur=str(e)[:100])
        raise HTTPException(502, str(e))
    audit("github.sync.ok", status="succes")
    return {"ok": True, "commits": commits}
