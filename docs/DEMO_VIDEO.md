# Script de la démo vidéo (≈ 6 minutes)

Cochez chaque critère de validation pendant l'enregistrement.

| Durée | Scène | Critère |
|---|---|---|
| 0:00 | Présenter l'architecture (diagramme de `docs/DOCUMENTATION.md`) : 6 agents sectoriels + monitoring | Architecture |
| 0:40 | VS Code : barre de titre 🤖, terminal d'accueil, lancer `python robot.py` | Robot |
| 1:10 | `POST /api/analyze/mines` (cas normal puis critique) ; montrer `X-Correlation-ID` dans la réponse | **Observabilité** |
| 2:00 | Monitoring (`/api/monitoring`) et audit (`/api/audit`) : retrouver le même correlation ID | **Observabilité** |
| 2:40 | `python -m pytest -q` : tous les tests passent ; onglet **Actions** GitHub vert | **Tests** |
| 3:20 | `GET /api/governance/check` et un fichier `agent_cards/*.json` : carte complète et à jour | **Gouvernance** |
| 3:50 | `docker build` / `docker compose up`, puis `/health` ; puis l'URL **Render** `/health` et `/docs` | **Conteneurisation et déploiement** |
| 4:40 | Incident : erreurs provoquées → `critical` → kill switch (503) → analyse par correlation ID → correction → réactivation | **Incident (runbook)** |
| 5:40 | Option GitHub : montrer qu'elle est désactivée par défaut, puis la synchronisation (dépôt privé, aucune donnée métier) | Option |
| 6:00 | Conclusion : limites (seuils illustratifs, validation humaine) | Documentation |

Pour la scène incident : `python robot.py` → menu **8** (simulation : 8 erreurs fictives, identifiées « SIM-… », injectées dans le monitoring en mémoire) → menu **2** : statut `critical` → menu **5** : kill switch → menu **1** : analyse refusée → menu **5** : réactiver. Dire clairement dans la vidéo qu'il s'agit d'une simulation.
