# Fil Obligataire — collecte publique

Collecte des RSS déclarés dans `sources.yaml`, indépendante des appareils du lecteur.

- Programmation toutes les 5 minutes entre 6 h et 22 h en semaine, heure de Paris (été/hiver), à partir de H:02 ; toutes les heures autrement.
- GitHub peut retarder ou omettre un passage. Ce n’est pas un service temps réel garanti. Un dépôt inactif pendant 60 jours peut voir ses tâches suspendues ; les mises à jour réelles de données entretiennent l’activité du dépôt.
- La branche `data` conserve le dernier `snapshot.json` et son historique Git. Le contenu courant est limité aux sept derniers jours. L’historique Git peut contenir des publications plus anciennes.
- Aucun secret, aucun portefeuille, aucune watchlist. Les règles privées sont appliquées par le site destinataire.
- Titre, extrait RSS court et lien seulement. Pas de scraping d’articles ni de contournement de robots.txt.
- Une source en panne ne bloque pas les autres ; les données précédentes sont conservées lors d’un échec global.
- Tests avant chaque collecte. `Actions` → `Collecter les flux publics` → `Run workflow` pour un lancement manuel.

Les runners standard Linux des dépôts publics sont gratuits. Aucun service payant, aucune clé API n’est nécessaire.
