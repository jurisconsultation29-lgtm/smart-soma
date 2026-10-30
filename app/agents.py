"""Architecture multi-agents par secteur + agent de monitoring + orchestrateur.
Aucune dépendance externe. Les seuils sont ILLUSTRATIFS : à calibrer et valider par des experts du secteur."""
import os
import time

from .observability import Monitor, audit, clean_corr, get_state

NEXT_REVIEW = os.environ.get("NEXT_REVIEW", "2027-01-31")
OWNER_BIZ = os.environ.get("OWNER_BUSINESS", "Responsable métier du secteur (à nommer)")
OWNER_TECH = os.environ.get("OWNER_TECH", "Équipe data et IA de l'établissement")
LEVELS = [(25, "faible"), (50, "modéré"), (75, "élevé"), (101, "critique")]
DISCLAIMER = "Aide à la décision : toute conclusion doit être validée par un professionnel du secteur."


class Suspended(Exception):
    """L'agent est suspendu par le kill switch."""


class UnknownSector(KeyError):
    pass


def check(payload, schema):
    """Valide l'entrée : champs présents, bons types, valeurs dans les plages. Lève ValueError sinon."""
    if not isinstance(payload, dict):
        raise ValueError("Le corps doit être un objet JSON")
    out = {}
    for k, (t, lo, hi) in schema.items():
        if k not in payload:
            raise ValueError(f"Champ manquant : {k}")
        v = payload[k]
        if t is bool:
            if not isinstance(v, bool):
                raise ValueError(f"{k} doit être vrai ou faux")
        elif t is list:
            if not isinstance(v, list) or len(v) > 20 or not all(isinstance(x, str) and len(x) <= 30 for x in v):
                raise ValueError(f"{k} doit être une liste de textes courts")
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError(f"{k} hors plage [{lo}, {hi}]")
        out[k] = v
    return out


class SectorAgent:
    id = sector = name = role = ""
    version = "1.0.0"
    schema = {}
    rules = []          # (condition, points, raison, recommandation)
    tools = ["Règles métier locales"]
    extra_limits = []

    def analyze(self, payload):
        d = check(payload, self.schema)
        score, reasons, recos = 0, [], []
        for cond, pts, why, reco in self.rules:
            if cond(d):
                score += pts
                reasons.append(why)
                recos.append(reco)
        score = min(score, 100)
        level = next(n for lim, n in LEVELS if score < lim)
        return {"sector": self.sector, "agent": self.id, "version": self.version, "score": score, "level": level,
                "reasons": reasons, "recommendations": recos or ["Aucune action particulière ; poursuivre la surveillance."],
                "requires_human_validation": True, "disclaimer": DISCLAIMER}

    def card(self):
        return {"id": self.id, "name": self.name, "sector": self.sector, "version": self.version,
                "versions_published": [self.version], "role": self.role, "business_owner": OWNER_BIZ,
                "technical_owner": OWNER_TECH, "tools": self.tools,
                "limits": ["Aide à la décision uniquement : validation humaine obligatoire.",
                           "Seuils illustratifs, à calibrer et valider par des experts du secteur.",
                           "Aucune donnée d'identité n'est journalisée.", *self.extra_limits],
                "guardrails": ["Validation stricte des entrées", "Correlation ID", "Journal d'audit chaîné", "Kill switch"],
                "next_review": NEXT_REVIEW}


class Mines(SectorAgent):
    id, sector, name = "MIN-001", "mines", "Agent Mines : sécurité des galeries"
    role = "Évalue le risque à partir du méthane, des vibrations et de la température."
    schema = {"methane_ppm": (float, 0, 100000), "vibration_mm_s": (float, 0, 200), "temperature_c": (float, -20, 100)}
    rules = [(lambda d: d["methane_ppm"] >= 5000, 60, "Méthane très élevé (>= 5000 ppm)", "Évacuer la zone et ventiler."),
             (lambda d: 2500 <= d["methane_ppm"] < 5000, 25, "Méthane élevé (2500 à 5000 ppm)", "Renforcer la ventilation et surveiller."),
             (lambda d: d["vibration_mm_s"] >= 20, 25, "Vibrations élevées (>= 20 mm/s)", "Inspecter la stabilité des galeries."),
             (lambda d: d["temperature_c"] >= 45, 20, "Température élevée (>= 45 °C)", "Limiter l'exposition du personnel.")]


class Sante(SectorAgent):
    id, sector, name = "SAN-001", "sante", "Agent Santé : orientation (sans diagnostic)"
    role = "Propose un niveau d'orientation à partir de la douleur, du sommeil et des signes d'alerte."
    schema = {"pain_0_10": (float, 0, 10), "sleep_hours": (float, 0, 24), "red_flags": (list, 0, 0)}
    extra_limits = ["Ne pose aucun diagnostic ; ne remplace pas un avis médical."]
    rules = [(lambda d: bool(set(d["red_flags"]) & {"chest_pain", "dyspnea", "stroke", "syncope", "suicidal"}), 100,
              "Signe d'alerte déclaré", "Évaluation médicale urgente (Maroc : SAMU 141, Protection civile 15)."),
             (lambda d: d["pain_0_10"] >= 7, 30, "Douleur intense (>= 7/10)", "Consultation médicale rapide."),
             (lambda d: 4 <= d["pain_0_10"] < 7, 15, "Douleur modérée", "Surveiller ; consulter si persistance."),
             (lambda d: d["sleep_hours"] < 5, 15, "Sommeil insuffisant (< 5 h)", "Évaluer le stress et l'hygiène de sommeil.")]


class Automobile(SectorAgent):
    id, sector, name = "AUT-001", "automobile", "Agent Automobile : diagnostic embarqué"
    role = "Évalue l'état du véhicule : température moteur, batterie, pneus, codes défaut."
    schema = {"engine_temp_c": (float, -40, 200), "battery_v": (float, 0, 30), "tire_pressure_bar": (float, 0, 6), "dtc_codes": (list, 0, 0)}
    rules = [(lambda d: d["engine_temp_c"] >= 110, 50, "Surchauffe moteur (>= 110 °C)", "Arrêt immédiat et contrôle du refroidissement."),
             (lambda d: 100 <= d["engine_temp_c"] < 110, 25, "Température moteur élevée", "Réduire la charge et contrôler."),
             (lambda d: d["battery_v"] < 11.8, 25, "Batterie faible (< 11,8 V)", "Tester batterie et alternateur."),
             (lambda d: d["tire_pressure_bar"] < 1.8, 25, "Pression des pneus basse (< 1,8 bar)", "Regonfler et vérifier les fuites."),
             (lambda d: len(d["dtc_codes"]) > 0, 20, "Codes défaut présents", "Lire et traiter les codes défaut.")]


class Finance(SectorAgent):
    id, sector, name = "FIN-001", "finance", "Agent Finance : risque de fraude"
    role = "Évalue le risque d'une transaction : montant, pays, vélocité, nouveau bénéficiaire."
    schema = {"amount": (float, 0, 1e9), "country_risk": (float, 0, 1), "tx_last_24h": (int, 0, 1000), "new_beneficiary": (bool, 0, 0)}
    rules = [(lambda d: d["amount"] >= 10000, 25, "Montant élevé (>= 10 000)", "Vérification renforcée."),
             (lambda d: d["country_risk"] >= 0.7, 30, "Pays à risque élevé", "Contrôle conformité (LAB-FT)."),
             (lambda d: d["tx_last_24h"] >= 10, 25, "Vélocité élevée (>= 10 opérations/24 h)", "Suspendre et contacter le client."),
             (lambda d: d["new_beneficiary"], 20, "Nouveau bénéficiaire", "Confirmation par un second canal.")]


class Energie(SectorAgent):
    id, sector, name = "ENE-001", "energie", "Agent Énergie : stabilité du réseau"
    role = "Évalue la stabilité du réseau : charge, fréquence, écart de tension."
    schema = {"load_pct": (float, 0, 200), "frequency_hz": (float, 40, 60), "voltage_dev_pct": (float, -50, 50)}
    rules = [(lambda d: abs(d["frequency_hz"] - 50) >= 0.5, 40, "Écart de fréquence >= 0,5 Hz", "Délestage ou appel de réserve."),
             (lambda d: 0.2 <= abs(d["frequency_hz"] - 50) < 0.5, 20, "Écart de fréquence modéré", "Activer la réserve primaire."),
             (lambda d: d["load_pct"] >= 95, 35, "Charge très élevée (>= 95 %)", "Délester les charges non critiques."),
             (lambda d: 85 <= d["load_pct"] < 95, 15, "Charge élevée", "Anticiper la production."),
             (lambda d: abs(d["voltage_dev_pct"]) >= 10, 25, "Écart de tension >= 10 %", "Contrôler les régleurs en charge.")]


class EGov(SectorAgent):
    id, sector, name = "GOV-001", "egov", "Agent e-Gov : recevabilité d'un dossier"
    role = "Aide à instruire un dossier : pièces, identité, cas sensible, similarité."
    schema = {"documents_complete": (bool, 0, 0), "identity_verified": (bool, 0, 0), "sensitive_case": (bool, 0, 0), "similarity_pct": (float, 0, 100)}
    extra_limits = ["Les cas sensibles (dérogation, bourse, handicap) exigent une étude humaine."]
    rules = [(lambda d: not d["identity_verified"], 40, "Identité non vérifiée", "Demander une pièce d'identité valide."),
             (lambda d: not d["documents_complete"], 30, "Pièces manquantes", "Relancer le demandeur."),
             (lambda d: d["sensitive_case"], 20, "Cas sensible", "Étude humaine obligatoire par la commission."),
             (lambda d: d["similarity_pct"] >= 60, 30, "Similarité élevée (>= 60 %)", "Vérifier l'originalité du dossier.")]


class MonitoringAgent:
    """Agent de monitoring : surveille les autres agents (KPI, latence, erreurs) et propose l'étape du runbook."""
    id, name, version = "MON-001", "Agent Monitoring : observabilité des agents", "1.0.0"
    sector = "monitoring"
    role = "Surveille taux d'erreur et latence de tous les agents, déclenche les alertes et recommande l'action du runbook."
    tools = ["Monitor (métriques en mémoire)", "Journal d'audit"]

    def check(self, monitor):
        s = monitor.stats()
        n, rate = s["executions"], s["taux_erreur"]
        if n >= 5 and rate >= 0.3:
            status, step = "critical", "Contention : activer le kill switch puis appliquer le runbook."
        elif s["alertes"] or rate >= 0.1:
            status, step = "degraded", "Détection : analyser les alertes et les logs avec le correlation ID."
        else:
            status, step = "ok", "Aucune action."
        return {"agent": self.id, "status": status, "prochaine_etape": step, **s}

    def card(self):
        return {"id": self.id, "name": self.name, "sector": self.sector, "version": self.version, "versions_published": [self.version],
                "role": self.role, "business_owner": OWNER_BIZ, "technical_owner": OWNER_TECH, "tools": self.tools,
                "limits": ["Ne corrige rien seul : propose une étape du runbook.", "Métriques en mémoire : perdues au redémarrage."],
                "guardrails": ["Aucune donnée métier lue", "Seuils configurables (LATENCY_ALERT_MS)"], "next_review": NEXT_REVIEW}


class Orchestrator:
    """Route une demande vers l'agent du secteur, mesure, journalise (correlation ID) et applique le kill switch."""
    def __init__(self, monitor=None):
        self.monitor = monitor or Monitor()
        self.agents = {a.sector: a for a in (Mines(), Sante(), Automobile(), Finance(), Energie(), EGov())}
        self.monitoring = MonitoringAgent()

    def all_cards(self):
        return [a.card() for a in self.agents.values()] + [self.monitoring.card()]

    def run(self, sector, payload, corr=None):
        corr = clean_corr(corr)
        if get_state()["kill"]:
            raise Suspended()
        agent = self.agents.get(sector)
        if agent is None:
            raise UnknownSector(sector)
        t0, status = time.perf_counter(), "succes"
        try:
            res = agent.analyze(payload)
        except ValueError:
            status = "refus"
            raise
        except Exception:
            status = "erreur"
            raise
        finally:
            ms = int((time.perf_counter() - t0) * 1000)
            self.monitor.record(agent.id, sector, status, ms, corr)
            audit("analyze", corr=corr, sector=sector, agent=agent.id, status=status, version=agent.version)
        return {"corr": corr, "latency_ms": ms, **res}
