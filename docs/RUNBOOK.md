# Runbook d'incident

Un incident = comportement inattendu d'un agent (réponse incorrecte, violation de policy, appel d'outil inattendu, KPI dégradé, alerte de latence).

| Étape | Actions |
|---|---|
| **1. Détection** | Alerte dans `GET /api/monitoring` (statut `degraded` ou `critical`) ou signalement. Noter le **correlation ID**. Chercher ce correlation ID dans `GET /api/audit`. |
| **2. Contention** | `POST /api/admin/kill-switch` avec `{"active": true, "reason": "incident <ID>"}` (en-tête `X-Admin-Token`). Les analyses répondent 503. Prévenir le responsable technique et le propriétaire métier. |
| **3. Remédiation** | Analyser les logs et l'audit (`GET /api/audit/verify` pour s'assurer de l'intégrité). Identifier la cause (règle, seuil, configuration, dépendance). Rollback : redéployer le dernier tag stable (`git checkout vX.Y.Z`, ou redéploiement Render de ce commit). |
| **4. Rétablissement** | Lancer `python -m pytest -q`. Désactiver le kill switch (`{"active": false}`). Réactiver progressivement ; surveiller `GET /api/monitoring` ; consigner l'incident (cause, correction, version). |

Équivalent dans le robot : `python robot.py` → menu 5 (kill switch) et menu 2 (monitoring).

## Scénario de démonstration
1. Provoquer des erreurs ou une latence (voir `docs/DEMO_VIDEO.md`) → alerte avec correlation ID.
2. Statut `critical` → activer le kill switch → vérifier le 503.
3. Corriger, tester, réactiver → `ok`.
