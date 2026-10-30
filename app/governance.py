"""Gouvernance : Agent Cards (complètes et à jour), runbook d'incident, génération des fichiers JSON.
Commande : python -m app.governance --write"""
import json
import sys
from datetime import date
from pathlib import Path

REQUIRED = ["id", "name", "sector", "version", "versions_published", "role", "business_owner",
            "technical_owner", "tools", "limits", "guardrails", "next_review"]

RUNBOOK = [
    {"etape": "1. Détection", "declencheurs": "Réponse incorrecte, violation de policy, appel d'outil inattendu, dégradation KPI, alerte de latence",
     "actions": "Relever le correlation ID de l'alerte ; consulter /api/monitoring et le journal d'audit"},
    {"etape": "2. Contention", "declencheurs": "Anomalie confirmée ou statut monitoring « critical »",
     "actions": "Activer le kill switch (POST /api/admin/kill-switch) ; suspendre les actions critiques ; prévenir l'équipe"},
    {"etape": "3. Remédiation", "declencheurs": "Agent isolé",
     "actions": "Analyser les logs par correlation ID ; identifier la cause ; rollback vers le dernier tag SemVer stable"},
    {"etape": "4. Rétablissement", "declencheurs": "Correctif validé",
     "actions": "Lancer les tests ; désactiver le kill switch ; réactiver progressivement ; surveillance renforcée ; consigner l'incident"},
]


def card_status(card, today=None):
    """Retourne si la carte est complète (tous les champs non vides) et à jour (revue non dépassée)."""
    today = today or date.today()
    missing = [k for k in REQUIRED if not card.get(k)]
    try:
        up = date.fromisoformat(card.get("next_review", "")) >= today
    except ValueError:
        up = False
    warnings = [f"{k} à nommer" for k in ("business_owner", "technical_owner") if "à nommer" in str(card.get(k, ""))]
    return {"id": card.get("id"), "complete": not missing, "missing": missing, "up_to_date": up, "warnings": warnings}


def write_cards(cards, folder="agent_cards"):
    Path(folder).mkdir(exist_ok=True)
    for c in cards:
        Path(folder, f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from .agents import Orchestrator
    if "--write" in sys.argv:
        write_cards(Orchestrator().all_cards())
        print("Agent Cards écrites dans agent_cards/")
