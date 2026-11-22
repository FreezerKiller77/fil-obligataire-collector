# Fil Obligataire — collecte publique

Collecte des RSS déclarés dans `sources.yaml`, même lorsque le site est fermé, sans appel à ChatGPT.

- Toutes les 10 minutes entre 6 h et 22 h en semaine (Europe/Paris, été/hiver), aux minutes 03, 13, 23, 33, 43, 53. Toutes les heures sinon, à la minute 02.
- GitHub peut retarder ou omettre un passage. Les planifications peuvent être suspendues après 60 jours d’inactivité : vérifier Actions.
- La branche `data` conserve `snapshot.json` avec sept jours glissants. L’historique Git peut conserver des publications plus anciennes.
- Le site privé importe les résultats à son ouverture et toutes les deux minutes pendant son utilisation. Son bouton manuel conserve sa collecte directe.
- Aucun secret, portefeuille ou watchlist dans ce dépôt. Les règles privées sont appliquées sur le site.
- Titres, courts extraits RSS et liens uniquement ; respect de robots.txt. Les données précédentes restent disponibles en cas d’échec global.
- Tests avant chaque collecte. Actions → Collecter les flux publics → Run workflow pour lancer une collecte. Workflow options → Disable workflow pour suspendre la planification.
- Pour ajouter un flux, conserver le même code et la même URL dans sources.yaml et dans CONFIG sur le site.

Les runners standard Linux des dépôts publics sont gratuits. Aucune clé API payante nécessaire. La tâche ChatGPT peut rester en pause.
