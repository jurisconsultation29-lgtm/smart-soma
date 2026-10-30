import json
from datetime import date
from pathlib import Path
from app.agents import Orchestrator
from app.governance import RUNBOOK, card_status


def test_agent_cards_completes_et_a_jour():
    for c in Orchestrator().all_cards():
        s = card_status(c, today=date(2026, 10, 30))
        assert s["complete"], (c["id"], s["missing"])
        assert s["up_to_date"], c["id"]


def test_carte_incomplete_detectee():
    c = Orchestrator().all_cards()[0]
    c["limits"] = []
    assert card_status(c)["missing"] == ["limits"]


def test_carte_perimee_detectee():
    c = Orchestrator().all_cards()[0]
    assert card_status(c, today=date(2030, 1, 1))["up_to_date"] is False


def test_fichiers_json_synchronises_avec_le_code():
    root = Path(__file__).resolve().parent.parent / "agent_cards"
    for c in Orchestrator().all_cards():
        assert json.loads((root / f"{c['id']}.json").read_text(encoding="utf-8")) == c, "Relancer : python -m app.governance --write"


def test_runbook_quatre_etapes():
    assert [r["etape"][:1] for r in RUNBOOK] == ["1", "2", "3", "4"]


def test_agents_sectoriels_et_monitoring_presents():
    ids = {c["id"] for c in Orchestrator().all_cards()}
    assert ids == {"MIN-001", "SAN-001", "AUT-001", "FIN-001", "ENE-001", "GOV-001", "MON-001"}
