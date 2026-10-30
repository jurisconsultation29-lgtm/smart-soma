import os
import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:      # FastAPI/httpx absents : ces tests s'exécutent dans la CI
    pytest.skip("fastapi ou httpx non installé", allow_module_level=True)

from app.main import app

K = {"X-API-Key": os.environ["AGENT_API_KEY"]}
A = {"X-Admin-Token": os.environ["ADMIN_TOKEN"]}
OK = {"methane_ppm": 100, "vibration_mm_s": 2, "temperature_c": 22}
c = TestClient(app)


def test_health_et_correlation_id():
    r = c.get("/health")
    assert r.status_code == 200 and r.headers["X-Correlation-ID"]
    assert c.get("/health", headers={"X-Correlation-ID": "MON-ID-123456"}).headers["X-Correlation-ID"] == "MON-ID-123456"


def test_analyse_sans_cle_refusee():
    assert c.post("/api/analyze/mines", json=OK).status_code == 401


def test_analyse_ok_avec_corr():
    r = c.post("/api/analyze/mines", json=OK, headers=K)
    assert r.status_code == 200 and r.json()["corr"] == r.headers["X-Correlation-ID"]


def test_entree_invalide_et_secteur_inconnu():
    assert c.post("/api/analyze/mines", json={"methane_ppm": 1}, headers=K).status_code == 422
    assert c.post("/api/analyze/peche", json=OK, headers=K).status_code == 404


def test_monitoring_reserve_admin():
    assert c.get("/api/monitoring").status_code == 401
    assert c.get("/api/monitoring", headers=A).json()["agent"] == "MON-001"


def test_agent_cards_et_gouvernance():
    assert len(c.get("/api/agents").json()) == 7
    assert c.get("/api/agent-card/MIN-001").json()["sector"] == "mines"
    assert all(s["complete"] for s in c.get("/api/governance/check").json())


def test_kill_switch_503_puis_reactivation():
    assert c.post("/api/admin/kill-switch", json={"active": True, "reason": "t"}, headers=A).json()["kill"] is True
    assert c.post("/api/analyze/mines", json=OK, headers=K).status_code == 503
    c.post("/api/admin/kill-switch", json={"active": False}, headers=A)
    assert c.post("/api/analyze/mines", json=OK, headers=K).status_code == 200


def test_option_github_desactivee_par_defaut():
    assert c.post("/api/admin/github/sync", headers=A).status_code == 501


def test_audit_chaine_valide():
    assert c.get("/api/audit/verify", headers=A).json()["valid"] is True
