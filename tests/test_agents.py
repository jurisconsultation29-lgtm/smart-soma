import pytest
from app.agents import Orchestrator, Suspended, UnknownSector
from app.observability import set_state

NORMAL = {
    "mines": {"methane_ppm": 300, "vibration_mm_s": 3, "temperature_c": 25},
    "sante": {"pain_0_10": 1, "sleep_hours": 8, "red_flags": []},
    "automobile": {"engine_temp_c": 90, "battery_v": 12.6, "tire_pressure_bar": 2.3, "dtc_codes": []},
    "finance": {"amount": 200, "country_risk": 0.1, "tx_last_24h": 1, "new_beneficiary": False},
    "energie": {"load_pct": 60, "frequency_hz": 50.0, "voltage_dev_pct": 1},
    "egov": {"documents_complete": True, "identity_verified": True, "sensitive_case": False, "similarity_pct": 10},
}
CRITIQUE = {
    "mines": {"methane_ppm": 9000, "vibration_mm_s": 40, "temperature_c": 50},
    "sante": {"pain_0_10": 9, "sleep_hours": 3, "red_flags": ["chest_pain"]},
    "automobile": {"engine_temp_c": 120, "battery_v": 10, "tire_pressure_bar": 1.0, "dtc_codes": ["P0300"]},
    "finance": {"amount": 50000, "country_risk": 0.9, "tx_last_24h": 20, "new_beneficiary": True},
    "energie": {"load_pct": 99, "frequency_hz": 49.2, "voltage_dev_pct": 15},
    "egov": {"documents_complete": False, "identity_verified": False, "sensitive_case": True, "similarity_pct": 80},
}


def test_six_secteurs_present():
    assert set(Orchestrator().agents) == set(NORMAL)


def test_cas_normal_faible_et_validation_humaine():
    o = Orchestrator()
    for sector, p in NORMAL.items():
        r = o.run(sector, p)
        assert r["level"] == "faible", sector
        assert r["requires_human_validation"] is True
        assert r["corr"]


def test_cas_critique():
    o = Orchestrator()
    for sector, p in CRITIQUE.items():
        r = o.run(sector, p)
        assert r["level"] == "critique", sector
        assert r["reasons"] and r["recommendations"]


def test_entree_invalide_refusee():
    o = Orchestrator()
    with pytest.raises(ValueError):
        o.run("mines", {"methane_ppm": 300})
    with pytest.raises(ValueError):
        o.run("mines", {"methane_ppm": -5, "vibration_mm_s": 1, "temperature_c": 20})
    with pytest.raises(ValueError):
        o.run("finance", {"amount": "beaucoup", "country_risk": 0.1, "tx_last_24h": 1, "new_beneficiary": False})


def test_secteur_inconnu():
    with pytest.raises(UnknownSector):
        Orchestrator().run("peche", {})


def test_kill_switch_suspend_les_agents():
    o = Orchestrator()
    set_state(True, "test")
    try:
        with pytest.raises(Suspended):
            o.run("mines", NORMAL["mines"])
    finally:
        set_state(False)
    assert o.run("mines", NORMAL["mines"])["level"] == "faible"
