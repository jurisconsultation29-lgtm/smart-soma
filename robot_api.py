"""
robot_api.py : l'API du robot 🤖 en UN SEUL FICHIER. Aucun module à installer (Python 3.8+ suffit).

Lancer :   python robot_api.py
Puis dans le robot (VS Code) : bouton « État ».   Page d'aide : http://127.0.0.1:8001

Variables facultatives : PORT (8001), PACK (secteurs | mine | all), AGENT_API_KEY, ADMIN_TOKEN.
Sans AGENT_API_KEY / ADMIN_TOKEN : clés de TEST locales acceptées (API écoute seulement sur 127.0.0.1).
"""
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = int(os.environ.get("PORT", "8001"))
PACK = os.environ.get("PACK", "secteurs")
KEY_ENV, ADMIN_ENV = os.environ.get("AGENT_API_KEY"), os.environ.get("ADMIN_TOKEN")
API_KEYS = {KEY_ENV} if KEY_ENV else {"dev-key", "cle-locale-de-test-2026"}
ADMIN_KEYS = {ADMIN_ENV} if ADMIN_ENV else {"dev-admin", "admin-local-de-test-2026"}
VERSION, NEXT_REVIEW = "1.0.0", os.environ.get("NEXT_REVIEW", "2027-01-31")
OWNER_BIZ = os.environ.get("OWNER_BUSINESS", "Responsable métier (à nommer)")
OWNER_TECH = os.environ.get("OWNER_TECH", "Équipe technique (à nommer)")
LATENCE_MS = int(os.environ.get("LATENCY_ALERT_MS", "5000"))
LEVELS = [(25, "faible"), (50, "modéré"), (75, "élevé"), (101, "critique")]
DISCLAIMER = ("Aide à la décision : ne remplace ni les détecteurs certifiés ni les procédures de "
              "sécurité ; toute décision revient à un professionnel du secteur.")
RUNBOOK = [
    {"etape": "1. Détection", "actions": "Alerte monitoring ou signalement ; relever le correlation ID ; consulter l'audit."},
    {"etape": "2. Contention", "actions": "Activer le kill switch ; suspendre les actions critiques ; prévenir l'équipe."},
    {"etape": "3. Remédiation", "actions": "Analyser les logs par correlation ID ; corriger ou revenir à la version stable ; relancer les tests."},
    {"etape": "4. Rétablissement", "actions": "Désactiver le kill switch ; réactiver progressivement ; surveillance renforcée."},
]


class Erreur(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def check(payload, schema):
    """Valide strictement l'entrée (champs, types, plages). Lève Erreur(422) sinon."""
    if not isinstance(payload, dict):
        raise Erreur(422, "Le corps doit être un objet JSON")
    out = {}
    for k, (t, lo, hi) in schema.items():
        if k not in payload:
            raise Erreur(422, "Champ manquant : " + k)
        v = payload[k]
        if t == "b":
            if not isinstance(v, bool):
                raise Erreur(422, k + " doit être vrai ou faux")
        elif t == "l":
            if not isinstance(v, list) or len(v) > 20 or not all(isinstance(x, str) and len(x) <= 30 for x in v):
                raise Erreur(422, k + " : liste de textes courts attendue")
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise Erreur(422, "%s hors plage [%s, %s]" % (k, lo, hi))
        out[k] = v
    return out


def A(id, sector, name, role, schema, rules, extra=()):
    return {"id": id, "sector": sector, "name": name, "role": role, "schema": schema, "rules": rules, "extra": list(extra)}


RED_SANTE = {"chest_pain", "dyspnea", "stroke", "syncope", "suicidal"}
RED_MINE = {"gas_alarm", "missing_worker", "collapse_signs", "fire", "flooding"}
PACK_SECTEURS = [
    A("MIN-001", "mines", "Agent Mines : sécurité des galeries", "Évalue méthane, vibrations, température.",
      {"methane_ppm": ("n", 0, 1e5), "vibration_mm_s": ("n", 0, 200), "temperature_c": ("n", -20, 100)},
      [(lambda d: d["methane_ppm"] >= 5000, 60, "Méthane très élevé (≥ 5000 ppm)", "Évacuer la zone et ventiler."),
       (lambda d: 2500 <= d["methane_ppm"] < 5000, 25, "Méthane élevé", "Renforcer la ventilation."),
       (lambda d: d["vibration_mm_s"] >= 20, 25, "Vibrations élevées (≥ 20 mm/s)", "Inspecter la stabilité des galeries."),
       (lambda d: d["temperature_c"] >= 45, 20, "Température élevée (≥ 45 °C)", "Limiter l'exposition du personnel.")]),
    A("SAN-001", "sante", "Agent Santé : orientation (sans diagnostic)", "Oriente selon douleur, sommeil, signes d'alerte.",
      {"pain_0_10": ("n", 0, 10), "sleep_hours": ("n", 0, 24), "red_flags": ("l", 0, 0)},
      [(lambda d: bool(set(d["red_flags"]) & RED_SANTE), 100, "Signe d'alerte déclaré", "Évaluation médicale urgente (Maroc : SAMU 141, Protection civile 15)."),
       (lambda d: d["pain_0_10"] >= 7, 30, "Douleur intense (≥ 7/10)", "Consultation médicale rapide."),
       (lambda d: 4 <= d["pain_0_10"] < 7, 15, "Douleur modérée", "Surveiller ; consulter si persistance."),
       (lambda d: d["sleep_hours"] < 5, 15, "Sommeil insuffisant (< 5 h)", "Évaluer stress et sommeil.")], ["Ne pose aucun diagnostic."]),
    A("AUT-001", "automobile", "Agent Automobile : diagnostic embarqué", "Évalue température moteur, batterie, pneus, codes défaut.",
      {"engine_temp_c": ("n", -40, 200), "battery_v": ("n", 0, 30), "tire_pressure_bar": ("n", 0, 6), "dtc_codes": ("l", 0, 0)},
      [(lambda d: d["engine_temp_c"] >= 110, 50, "Surchauffe moteur (≥ 110 °C)", "Arrêt immédiat."),
       (lambda d: 100 <= d["engine_temp_c"] < 110, 25, "Température moteur élevée", "Réduire la charge."),
       (lambda d: d["battery_v"] < 11.8, 25, "Batterie faible (< 11,8 V)", "Tester batterie et alternateur."),
       (lambda d: d["tire_pressure_bar"] < 1.8, 25, "Pneus sous-gonflés (< 1,8 bar)", "Regonfler et chercher une fuite."),
       (lambda d: len(d["dtc_codes"]) > 0, 20, "Codes défaut présents", "Lire les codes défaut.")]),
    A("FIN-001", "finance", "Agent Finance : risque de fraude", "Évalue montant, pays, vélocité, nouveau bénéficiaire.",
      {"amount": ("n", 0, 1e9), "country_risk": ("n", 0, 1), "tx_last_24h": ("n", 0, 1000), "new_beneficiary": ("b", 0, 0)},
      [(lambda d: d["amount"] >= 10000, 25, "Montant élevé (≥ 10 000)", "Vérification renforcée."),
       (lambda d: d["country_risk"] >= 0.7, 30, "Pays à risque élevé", "Contrôle de conformité."),
       (lambda d: d["tx_last_24h"] >= 10, 25, "Vélocité élevée (≥ 10 opérations/24 h)", "Suspendre et contacter le client."),
       (lambda d: d["new_beneficiary"], 20, "Nouveau bénéficiaire", "Confirmation par un second canal.")]),
    A("ENE-001", "energie", "Agent Énergie : stabilité du réseau", "Évalue charge, fréquence, écart de tension.",
      {"load_pct": ("n", 0, 200), "frequency_hz": ("n", 40, 60), "voltage_dev_pct": ("n", -50, 50)},
      [(lambda d: abs(d["frequency_hz"] - 50) >= 0.5, 40, "Écart de fréquence ≥ 0,5 Hz", "Délestage ou appel de réserve."),
       (lambda d: 0.2 <= abs(d["frequency_hz"] - 50) < 0.5, 20, "Écart de fréquence modéré", "Activer la réserve primaire."),
       (lambda d: d["load_pct"] >= 95, 35, "Charge très élevée (≥ 95 %)", "Délester les charges non critiques."),
       (lambda d: 85 <= d["load_pct"] < 95, 15, "Charge élevée", "Anticiper la production."),
       (lambda d: abs(d["voltage_dev_pct"]) >= 10, 25, "Écart de tension ≥ 10 %", "Contrôler les régleurs en charge.")]),
    A("GOV-001", "egov", "Agent e-Gov : recevabilité d'un dossier", "Aide à instruire un dossier.",
      {"documents_complete": ("b", 0, 0), "identity_verified": ("b", 0, 0), "sensitive_case": ("b", 0, 0), "similarity_pct": ("n", 0, 100)},
      [(lambda d: not d["identity_verified"], 40, "Identité non vérifiée", "Demander une pièce d'identité valide."),
       (lambda d: not d["documents_complete"], 30, "Pièces manquantes", "Relancer le demandeur."),
       (lambda d: d["sensitive_case"], 20, "Cas sensible", "Étude humaine obligatoire."),
       (lambda d: d["similarity_pct"] >= 60, 30, "Similarité élevée (≥ 60 %)", "Vérifier l'originalité.")],
      ["Les cas sensibles exigent une étude humaine."]),
]
PACK_MINE = [
    A("VEN-001", "ventilation", "Agent Ventilation et gaz", "Évalue méthane, CO, oxygène, débit d'air.",
      {"methane_ppm": ("n", 0, 1e5), "co_ppm": ("n", 0, 1000), "oxygen_pct": ("n", 0, 25), "airflow_m3_s": ("n", 0, 500)},
      [(lambda d: d["methane_ppm"] >= 10000, 60, "Méthane ≥ 1 % (10 000 ppm)", "Couper l'énergie non certifiée, évacuer, ventiler."),
       (lambda d: 5000 <= d["methane_ppm"] < 10000, 30, "Méthane de 0,5 à 1 %", "Renforcer la ventilation."),
       (lambda d: d["co_ppm"] >= 50, 30, "CO ≥ 50 ppm", "Rechercher un échauffement ou un incendie."),
       (lambda d: d["oxygen_pct"] < 19.5, 40, "Oxygène < 19,5 %", "Évacuer la zone appauvrie."),
       (lambda d: d["airflow_m3_s"] < 10, 25, "Débit d'air insuffisant (< 10 m³/s)", "Contrôler les ventilateurs.")]),
    A("GEO-001", "geotechnique", "Agent Géotechnique : stabilité du massif", "Évalue vibrations, convergence, eau, chutes de blocs.",
      {"vibration_mm_s": ("n", 0, 200), "convergence_mm_day": ("n", 0, 100), "water_inflow_l_min": ("n", 0, 10000), "rockfall_events_24h": ("n", 0, 1000)},
      [(lambda d: d["convergence_mm_day"] >= 5, 40, "Convergence ≥ 5 mm/jour", "Interdire l'accès, inspecter le soutènement."),
       (lambda d: 2 <= d["convergence_mm_day"] < 5, 20, "Convergence de 2 à 5 mm/jour", "Surveiller la topographie."),
       (lambda d: d["vibration_mm_s"] >= 20, 25, "Vibrations élevées (≥ 20 mm/s)", "Inspecter la stabilité."),
       (lambda d: d["water_inflow_l_min"] >= 500, 25, "Venue d'eau forte (≥ 500 l/min)", "Contrôler le pompage."),
       (lambda d: d["rockfall_events_24h"] >= 3, 30, "Chutes de blocs répétées (≥ 3/24 h)", "Purger et réévaluer le soutènement.")]),
    A("EQP-001", "equipements", "Agent Équipements : état des engins", "Évalue température, vibration, hydraulique, maintenance.",
      {"engine_temp_c": ("n", 0, 150), "bearing_vibration_mm_s": ("n", 0, 50), "hydraulic_pressure_bar": ("n", 0, 500), "hours_since_maintenance": ("n", 0, 5000)},
      [(lambda d: d["engine_temp_c"] >= 105, 40, "Surchauffe moteur (≥ 105 °C)", "Arrêter l'engin."),
       (lambda d: d["bearing_vibration_mm_s"] >= 7, 30, "Vibration de roulement élevée (≥ 7 mm/s)", "Planifier le remplacement."),
       (lambda d: d["hydraulic_pressure_bar"] < 150, 25, "Pression hydraulique basse (< 150 bar)", "Rechercher une fuite."),
       (lambda d: d["hours_since_maintenance"] >= 500, 25, "Maintenance en retard (≥ 500 h)", "Planifier la maintenance.")]),
    A("SST-001", "sst", "Agent Santé-sécurité du personnel", "Évalue poussières, bruit, durée de poste, EPI, alertes.",
      {"dust_mg_m3": ("n", 0, 50), "noise_db": ("n", 30, 140), "shift_hours": ("n", 0, 24), "ppe_compliance_pct": ("n", 0, 100), "incident_flags": ("l", 0, 0)},
      [(lambda d: bool(set(d["incident_flags"]) & RED_MINE), 100, "Alerte de sécurité déclarée", "Déclencher le plan d'urgence selon la procédure de la mine."),
       (lambda d: d["dust_mg_m3"] >= 3, 25, "Poussières élevées (≥ 3 mg/m³)", "Renforcer l'arrosage et la protection."),
       (lambda d: d["noise_db"] >= 85, 20, "Bruit ≥ 85 dB(A)", "Imposer la protection auditive."),
       (lambda d: d["shift_hours"] > 10, 20, "Poste long (> 10 h)", "Limiter la durée d'exposition."),
       (lambda d: d["ppe_compliance_pct"] < 90, 25, "Port des EPI insuffisant (< 90 %)", "Contrôler les EPI.")]),
    A("ENV-001", "environnement", "Agent Environnement : eau, poussières, résidus", "Évalue pH, turbidité, PM10, bassin de résidus.",
      {"ph": ("n", 0, 14), "turbidity_ntu": ("n", 0, 1000), "pm10_ug_m3": ("n", 0, 1000), "tailings_level_pct": ("n", 0, 100)},
      [(lambda d: d["ph"] < 6 or d["ph"] > 9, 30, "pH hors de la plage 6 à 9", "Stopper le rejet et neutraliser."),
       (lambda d: d["turbidity_ntu"] >= 50, 20, "Turbidité élevée (≥ 50 NTU)", "Contrôler la décantation."),
       (lambda d: d["pm10_ug_m3"] >= 150, 25, "PM10 ≥ 150 µg/m³", "Arroser les pistes."),
       (lambda d: d["tailings_level_pct"] >= 90, 40, "Bassin de résidus presque plein (≥ 90 %)", "Alerter le responsable de la digue."),
       (lambda d: 80 <= d["tailings_level_pct"] < 90, 20, "Bassin de résidus à 80-90 %", "Planifier la vidange.")]),
    A("TIR-001", "tirs", "Agent Tirs et explosifs", "Évalue vibrations, distance, charge, raté de tir, vent.",
      {"ppv_mm_s": ("n", 0, 500), "distance_m": ("n", 0, 5000), "charge_kg_per_delay": ("n", 0, 5000), "misfire": ("b", 0, 0), "wind_towards_village": ("b", 0, 0)},
      [(lambda d: d["misfire"], 60, "Raté de tir déclaré", "Interdire l'accès, appliquer la procédure de raté de tir."),
       (lambda d: d["ppv_mm_s"] >= 50, 35, "Vibrations de tir élevées (≥ 50 mm/s)", "Revoir le plan de tir."),
       (lambda d: d["charge_kg_per_delay"] >= 500 and d["distance_m"] < 300, 25, "Charge élevée à faible distance", "Réduire la charge par retard."),
       (lambda d: d["wind_towards_village"], 15, "Vent vers les habitations", "Reporter le tir ou protéger.")],
      ["Ne remplace pas le boutefeu."]),
]
AGENTS = {a["sector"]: a for a in ({"secteurs": PACK_SECTEURS, "mine": PACK_MINE, "all": PACK_SECTEURS + PACK_MINE}.get(PACK, PACK_SECTEURS))}

# ------------------------------------------------------------------ état (en mémoire) : exécutions, alertes, audit, kill switch
LOCK, RUNS, ALERTS, CHAIN, ETAT, FAULTS = threading.Lock(), [], [], [], {"kill": False, "reason": ""}, set()


def sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def audit(event, **f):
    with LOCK:
        e = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **f, "prev": CHAIN[-1]["hash"] if CHAIN else "0" * 64}
        e["hash"] = sha(e)
        CHAIN.append(e)


def verify():
    prev = "0" * 64
    for i, e in enumerate(CHAIN):
        if e["prev"] != prev or sha({k: v for k, v in e.items() if k != "hash"}) != e["hash"]:
            return {"valid": False, "broken_at": i}
        prev = e["hash"]
    return {"valid": True, "entries": len(CHAIN)}


def corr_ok(v):
    return v if v and re.fullmatch(r"[A-Za-z0-9_-]{6,40}", v) else "API-" + uuid.uuid4().hex[:8]


def run(sector, payload, corr):
    if ETAT["kill"]:
        raise Erreur(503, "Agents suspendus (kill switch actif)")
    a = AGENTS.get(sector)
    if not a:
        raise Erreur(404, "Secteur inconnu")
    t0, statut, err, res = time.perf_counter(), "succes", None, None
    try:
        if sector in FAULTS:
            raise RuntimeError("Panne injectée")
        d = check(payload, a["schema"])
        score, why, reco = 0, [], []
        for cond, pts, w, r in a["rules"]:
            if cond(d):
                score += pts
                why.append(w)
                reco.append(r)
        score = min(score, 100)
        res = {"sector": sector, "agent": a["id"], "version": VERSION, "score": score, "level": next(n for lim, n in LEVELS if score < lim),
               "reasons": why, "recommendations": reco or ["Aucune action particulière ; poursuivre la surveillance."],
               "requires_human_validation": True, "disclaimer": DISCLAIMER}
    except Erreur as e:
        statut, err = "refus", e
    except Exception as e:
        statut, err = "erreur", e
    ms = int((time.perf_counter() - t0) * 1000)
    RUNS.append({"corr": corr, "agent": a["id"], "statut": statut, "ms": ms})
    del RUNS[:-500]
    if statut == "erreur" or ms > LATENCE_MS:
        ALERTS.append({"corr": corr, "agent": a["id"], "statut": statut, "ms": ms, "action": "Appliquer le runbook"})
    audit("analyze", corr=corr, sector=sector, agent=a["id"], statut=statut, version=VERSION)   # jamais les valeurs
    if isinstance(err, Erreur):
        raise err
    if err:
        raise Erreur(500, "Incident : " + str(err))
    return {"corr": corr, "latency_ms": ms, **res}


def monitoring():
    ok = [r for r in RUNS if r["statut"] == "succes"]
    er = [r for r in RUNS if r["statut"] == "erreur"]
    taux = round(len(er) / len(RUNS), 3) if RUNS else 0.0
    st, nxt = "ok", "Aucune action."
    if len(RUNS) >= 5 and taux >= 0.3:
        st, nxt = "critical", "Contention : activer le kill switch puis appliquer le runbook."
    elif ALERTS or taux >= 0.1:
        st, nxt = "degraded", "Détection : analyser les alertes avec le correlation ID."
    return {"agent": "MON-001", "status": st, "prochaine_etape": nxt, "executions": len(RUNS), "succes": len(ok), "erreurs": len(er),
            "taux_erreur": taux, "latence_moyenne_ms": int(sum(r["ms"] for r in ok) / len(ok)) if ok else 0, "alertes": ALERTS[-5:]}


def cartes():
    base = lambda i, s, n, r, ex=(), tools=("Règles métier locales",): {
        "id": i, "name": n, "sector": s, "version": VERSION, "versions_published": [VERSION], "role": r, "business_owner": OWNER_BIZ,
        "technical_owner": OWNER_TECH, "tools": list(tools),
        "limits": ["Aide à la décision : validation humaine obligatoire.", "Seuils illustratifs : à valider par un expert du secteur.",
                   "Aucune donnée métier n'est journalisée.", *ex],
        "guardrails": ["Validation stricte des entrées", "Correlation ID", "Journal d'audit chaîné", "Kill switch"], "next_review": NEXT_REVIEW}
    return [base(a["id"], a["sector"], a["name"], a["role"], a["extra"]) for a in AGENTS.values()] + [
        base("MON-001", "monitoring", "Agent Monitoring", "Surveille erreurs et latence ; recommande l'étape du runbook.", ("Ne corrige rien seul.",), ("Métriques en mémoire",))]


def statut_carte(c):
    manque = [k for k in ("id", "name", "sector", "version", "versions_published", "role", "business_owner", "technical_owner", "tools", "limits", "guardrails", "next_review") if not c.get(k)]
    try:
        a_jour = date.fromisoformat(c["next_review"]) >= date.today()
    except ValueError:
        a_jour = False
    return {"id": c["id"], "complete": not manque, "missing": manque, "up_to_date": a_jour,
            "warnings": [k + " à nommer" for k in ("business_owner", "technical_owner") if "à nommer" in c[k]]}


def eq(a, ens):
    return any(hmac.compare_digest(str(a or ""), k) for k in ens)


PAGE = """<!DOCTYPE html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>API du robot</title>
<body style="font:15px system-ui;max-width:760px;margin:20px auto;padding:0 12px"><h1>🤖 API du robot : en ligne</h1>
<p>Version %s · pack <b>%s</b> · %d agents + monitoring. Ouvrez le robot dans VS Code et cliquez <b>État</b>.</p>
<h3>Agents</h3><ul>%s</ul>
<h3>Routes</h3><pre>GET  /health
GET  /api/agents          GET /api/agent-card/{id}
GET  /api/governance/check   GET /api/runbook
POST /api/analyze/{secteur}      (en-tête X-API-Key)
GET  /api/monitoring   GET /api/audit/verify   (X-Admin-Token)
POST /api/admin/kill-switch  {"active": true}  (X-Admin-Token)</pre>
<p>Clés de test locales : <code>dev-key</code> / <code>dev-admin</code> (sans variables d'environnement).</p></body></html>"""


class H(BaseHTTPRequestHandler):
    server_version = "robot-api/1.0"

    def log_message(self, *a):
        pass

    def out(self, code, obj, corr):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Correlation-ID", corr)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)
        print("[%s] %s %s -> %s" % (corr, self.command, self.path, code), flush=True)

    def route(self):
        corr, p = corr_ok(self.headers.get("X-Correlation-ID")), self.path.split("?")[0].rstrip("/") or "/"
        try:
            if self.command == "GET" and p in ("/", "/docs"):
                html = PAGE % (VERSION, PACK, len(AGENTS), "".join("<li>%s : %s</li>" % (a["id"], a["sector"]) for a in AGENTS.values())) .encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            adm = lambda: (_ for _ in ()).throw(Erreur(401, "Jeton d'administration invalide")) if not eq(self.headers.get("X-Admin-Token"), ADMIN_KEYS) else None
            body = {}
            if self.command == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 65536:
                    raise Erreur(413, "Corps trop volumineux")
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    raise Erreur(400, "JSON invalide")
            if self.command == "GET":
                if p == "/health":
                    return self.out(200, {"ok": True, "version": VERSION, "kill_switch": ETAT["kill"]}, corr)
                if p == "/api/agents":
                    return self.out(200, [{"id": c["id"], "sector": c["sector"], "version": c["version"]} for c in cartes()], corr)
                m = re.fullmatch(r"/api/agent-card/([\w-]+)", p)
                if m:
                    c = next((x for x in cartes() if x["id"] == m.group(1)), None)
                    if not c:
                        raise Erreur(404, "Agent inconnu")
                    return self.out(200, c, corr)
                if p == "/api/governance/check":
                    return self.out(200, [statut_carte(c) for c in cartes()], corr)
                if p == "/api/runbook":
                    return self.out(200, RUNBOOK, corr)
                if p == "/api/monitoring":
                    adm()
                    return self.out(200, monitoring(), corr)
                if p == "/api/audit/verify":
                    adm()
                    return self.out(200, verify(), corr)
            elif self.command == "POST":
                m = re.fullmatch(r"/api/analyze/(\w+)", p)
                if m:
                    if not eq(self.headers.get("X-API-Key"), API_KEYS):
                        raise Erreur(401, "Clé d'API invalide")
                    return self.out(200, run(m.group(1), body, corr), corr)
                if p == "/api/admin/kill-switch":
                    adm()
                    ETAT.update(kill=bool(body.get("active")), reason=str(body.get("reason", ""))[:200])
                    audit("kill_switch", active=ETAT["kill"])
                    return self.out(200, {"kill": ETAT["kill"], "reason": ETAT["reason"]}, corr)
                if p == "/api/admin/github/sync":
                    adm()
                    raise Erreur(501, "Option GitHub non incluse dans ce fichier")
            raise Erreur(404, "Introuvable")
        except Erreur as e:
            self.out(e.code, {"detail": e.msg}, corr)
        except Exception as e:                       # jamais de plantage silencieux
            self.out(500, {"detail": "Erreur interne : " + str(e)}, corr)

    do_GET = do_POST = route


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("🤖 API du robot en ligne : http://127.0.0.1:%d  (pack %s, %d agents)" % (PORT, PACK, len(AGENTS)))
    print("   Clés de test : dev-key / dev-admin  (Ctrl+C pour arrêter)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n🤖 API arrêtée.")
