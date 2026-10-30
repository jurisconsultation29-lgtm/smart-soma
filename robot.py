"""
robot.py : le robot 🤖 du projet. Aucun module à installer pour l'utiliser.
Lancer (terminal VS Code, dossier du projet) :   python robot.py
Il pilote directement les agents : analyses par secteur, monitoring, gouvernance, audit, incident, tests, GitHub (option).
"""
import json
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")        # pour afficher 🤖 sous Windows
except Exception:
    pass

from app import governance, github_sync
from app.agents import Orchestrator, Suspended
from app.observability import get_state, new_corr, read_audit, set_state, verify_chain

ART = r"""
   ,--.
.--|__|--.     🤖  Robot multi-agents  (mines · santé · auto · finance · énergie · e-Gov)
|  o  o  |     Chaque exécution porte un correlation ID. Validation humaine toujours requise.
'--------'
"""
EX = {  # (exemple normal, exemple critique)
    "mines": ({"methane_ppm": 300, "vibration_mm_s": 3, "temperature_c": 25}, {"methane_ppm": 9000, "vibration_mm_s": 40, "temperature_c": 50}),
    "sante": ({"pain_0_10": 1, "sleep_hours": 8, "red_flags": []}, {"pain_0_10": 9, "sleep_hours": 3, "red_flags": ["chest_pain"]}),
    "automobile": ({"engine_temp_c": 90, "battery_v": 12.6, "tire_pressure_bar": 2.3, "dtc_codes": []}, {"engine_temp_c": 120, "battery_v": 10, "tire_pressure_bar": 1.0, "dtc_codes": ["P0300"]}),
    "finance": ({"amount": 200, "country_risk": 0.1, "tx_last_24h": 1, "new_beneficiary": False}, {"amount": 50000, "country_risk": 0.9, "tx_last_24h": 20, "new_beneficiary": True}),
    "energie": ({"load_pct": 60, "frequency_hz": 50.0, "voltage_dev_pct": 1}, {"load_pct": 99, "frequency_hz": 49.2, "voltage_dev_pct": 15}),
    "egov": ({"documents_complete": True, "identity_verified": True, "sensitive_case": False, "similarity_pct": 10}, {"documents_complete": False, "identity_verified": False, "sensitive_case": True, "similarity_pct": 80}),
}
O = Orchestrator()


def robot(msg):
    print("\n🤖", msg)


def ask(q):
    try:
        return input("👉 " + q + " ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n🤖 À bientôt !")
        sys.exit(0)


def saisie(agent):
    """Demande chaque champ du secteur (le robot guide le débutant)."""
    p = {}
    for k, (t, lo, hi) in agent.schema.items():
        if t is bool:
            p[k] = ask(f"{k} (o/n) :").lower().startswith("o")
        elif t is list:
            p[k] = [x.strip() for x in ask(f"{k} (séparés par des virgules, vide = aucun) :").split(",") if x.strip()]
        else:
            while True:
                try:
                    p[k] = float(ask(f"{k} (entre {lo} et {hi}) :").replace(",", "."))
                    break
                except ValueError:
                    robot("Tapez un nombre.")
    return p


def analyser():
    secteurs = list(O.agents)
    for i, s in enumerate(secteurs, 1):
        print(f"  {i}. {s}  ({O.agents[s].name})")
    c = ask("Numéro du secteur :")
    if not c.isdigit() or not 1 <= int(c) <= len(secteurs):
        return robot("Choix non reconnu.")
    s = secteurs[int(c) - 1]
    m = ask("1 = exemple normal, 2 = exemple critique, 3 = je saisis les valeurs :")
    p = {"1": EX[s][0], "2": EX[s][1]}.get(m) or saisie(O.agents[s])
    try:
        r = O.run(s, p)
    except Suspended:
        return robot("⛔ Agents suspendus (kill switch). Réactivez-les dans le menu 5.")
    except ValueError as e:
        return robot(f"Entrée refusée : {e}")
    robot(f"[{r['corr']}] {r['agent']} → niveau {r['level'].upper()} (score {r['score']}/100) en {r['latency_ms']} ms")
    for why in r["reasons"]:
        print("   -", why)
    for reco in r["recommendations"]:
        print("   →", reco)
    print("   ", r["disclaimer"])


def monitoring():
    r = O.monitoring.check(O.monitor)
    robot(f"Monitoring : {r['status'].upper()}  ·  {r['executions']} exécutions  ·  erreurs {r['erreurs']}  ·  latence moyenne {r['latence_moyenne_ms']} ms")
    print("   Prochaine étape :", r["prochaine_etape"])
    for a in r["alertes"]:
        print("   ⚠", a["corr"], a["agent"], a["status"], a["ms"], "ms")


def gouvernance():
    robot("Agent Cards (complètes et à jour ?)")
    for c in O.all_cards():
        s = governance.card_status(c)
        print(f"  {c['id']}  {c['sector']:<11} complète={s['complete']}  à jour={s['up_to_date']}  {' '.join(s['warnings'])}")
    print("   Pour régénérer les fichiers : python -m app.governance --write")


def journal():
    v = verify_chain()
    robot("✅ Chaîne d'audit intègre : %s entrées" % v["entries"] if v["valid"] else "⚠ Chaîne rompue à l'entrée %s" % v["broken_at"])
    for e in read_audit()[-5:]:
        print("  ", e["ts"][:19], e["event"], e.get("corr", ""))


def incident():
    robot("Runbook d'incident :")
    for r in governance.RUNBOOK:
        print("  ", r["etape"], ":", r["actions"])
    etat = get_state()
    robot("Agents actuellement : " + ("⛔ SUSPENDUS" if etat["kill"] else "✅ ACTIFS"))
    c = ask("S = suspendre (kill switch), R = réactiver, autre = rien :").lower()
    if c in ("s", "r"):
        set_state(c == "s", "action depuis robot.py")
        robot("⛔ Suspendus." if c == "s" else "✅ Réactivés.")


def simuler():
    """DÉMO uniquement : injecte de fausses erreurs dans le monitoring (en mémoire) pour montrer un incident."""
    for _ in range(8):
        O.monitor.record("FIN-001", "finance", "erreur", 10, new_corr("SIM"))
    robot("Simulation : 8 erreurs FICTIVES (correlation ID « SIM-… ») injectées dans le monitoring. Tapez 2 pour voir le statut, puis 5 pour le kill switch.")


def tests():
    robot("Je lance les tests automatiques (pytest)…")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    if r.returncode == 1:
        robot("Des tests échouent : lisez le message ci-dessus.")
    elif r.returncode not in (0, 5):
        robot("pytest n'est pas prêt. Tapez :  pip install -r requirements-dev.txt")
    else:
        robot("✅ Tests réussis.")


def github():
    robot("GitHub (OPTION, désactivée par défaut)")
    if not github_sync.enabled():
        print("   Pour l'activer : variables GITHUB_SYNC=1, GITHUB_TOKEN, GITHUB_REPO (dépôt PRIVÉ). Voir le README. Rien n'est envoyé.")
        return
    if ask("Envoyer Agent Cards, audit (métadonnées) et métriques vers GitHub ? (o/n)").lower() != "o":
        return
    try:
        r = github_sync.push(O.all_cards(), O.monitor.stats())
        robot("✅ Synchronisé : " + ", ".join(r))
    except Exception as e:
        robot("Échec : " + str(e))


MENU = [("1", "Analyser un secteur", analyser), ("2", "Monitoring (agent de surveillance)", monitoring),
        ("3", "Gouvernance : Agent Cards", gouvernance), ("4", "Journal d'audit", journal),
        ("5", "Incident : runbook et kill switch", incident), ("6", "Lancer les tests", tests),
        ("7", "GitHub (option)", github), ("8", "Simuler un incident (démo vidéo)", simuler)]

if __name__ == "__main__":
    print(ART)
    if "--hello" in sys.argv:
        robot("Bonjour ! Tapez  python robot.py  pour me parler, ou  Terminal > Exécuter la tâche > 🤖  pour mes raccourcis.")
        sys.exit(0)
    robot("Bonjour ! Que voulez-vous faire ?")
    while True:
        print()
        for k, n, _ in MENU:
            print(f"  {k}. {n}")
        print("  0. Quitter")
        c = ask("Votre choix :")
        if c == "0":
            robot("À bientôt 👋")
            break
        f = {k: fn for k, _, fn in MENU}.get(c)
        f() if f else robot("Tapez un chiffre du menu.")
