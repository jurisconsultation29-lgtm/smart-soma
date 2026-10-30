import json
from app.agents import MonitoringAgent, Orchestrator
from app.observability import Monitor, audit, clean_corr, data_dir, new_corr, verify_chain
from tests.test_agents import NORMAL


def test_correlation_id_unique_et_sur():
    ids = {new_corr() for _ in range(200)}
    assert len(ids) == 200
    assert clean_corr("abc<script>") != "abc<script>"
    assert clean_corr("REQ-12345678") == "REQ-12345678"


def test_correlation_id_sur_chaque_execution():
    o = Orchestrator()
    r1, r2 = o.run("sante", NORMAL["sante"]), o.run("sante", NORMAL["sante"], "MON-CORR-001")
    assert r1["corr"].startswith("API-") and r2["corr"] == "MON-CORR-001"


def test_alerte_de_latence_et_derreur():
    m = Monitor(latency_ms=100)
    m.record("MIN-001", "mines", "succes", 50, "A-000001")
    assert not m.alerts
    m.record("MIN-001", "mines", "succes", 500, "A-000002")
    m.record("MIN-001", "mines", "erreur", 10, "A-000003")
    assert len(m.alerts) == 2 and m.stats()["taux_erreur"] > 0


def test_agent_monitoring_statuts():
    ag, m = MonitoringAgent(), Monitor(latency_ms=100)
    assert ag.check(m)["status"] == "ok"
    for i in range(10):
        m.record("FIN-001", "finance", "erreur", 5, f"E-00000{i}")
    r = ag.check(m)
    assert r["status"] == "critical" and "kill switch" in r["prochaine_etape"]


def test_audit_chaine_et_altération_detectee():
    audit("test", corr="T-00000001")
    audit("test", corr="T-00000002")
    assert verify_chain()["valid"] is True
    f = data_dir() / "audit.jsonl"
    lines = f.read_text().splitlines()
    e = json.loads(lines[-2])
    e["corr"] = "FALSIFIE"
    lines[-2] = json.dumps(e)
    f.write_text("\n".join(lines) + "\n")
    assert verify_chain()["valid"] is False
    f.unlink()


def test_laudit_ne_contient_aucune_donnee_metier():
    o = Orchestrator()
    o.run("sante", {"pain_0_10": 3, "sleep_hours": 6, "red_flags": ["stroke"]}, "PRIV-0000001")
    texte = (data_dir() / "audit.jsonl").read_text()
    assert "stroke" not in texte and "pain_0_10" not in texte
