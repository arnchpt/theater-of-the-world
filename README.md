# Theater of the World

Baromètre hebdomadaire des relations internationales : une carte du monde où chaque relation entre deux pays est notée de −10 (conflit armé) à +10 (alliance), mise à jour chaque matin à partir des événements codés par [GDELT](https://www.gdeltproject.org).

## Structure

| Chemin | Rôle |
|---|---|
| `src/theater-of-the-world.html` | La page (carte, panneaux, calcul des notes). Fonctionne seule avec un jeu d’exemple, ou avec `data/latest.json` quand il existe. |
| `pipeline/update.py` | Collecte et agrégation, en Python standard (aucune dépendance). |
| `data/days/` | Agrégats quotidiens (paires de pays, articles les plus repris, lieux de violence), versionnés. |
| `data/weeks/` | Agrégats par semaine ISO, versionnés. |
| `site/` | Site généré (`index.html` + `data/latest.json`), non versionné, publié par GitHub Pages. |
| `.github/workflows/daily.yml` | Exécution quotidienne à 07:30 UTC, archivage des agrégats et déploiement. |

## Lancer en local

```bash
python3 -I pipeline/update.py
```

Sans argument, le script télécharge les jours manquants jusqu’à hier (environ 8 Mo par jour), met à jour les agrégats et reconstruit `site/`. Options utiles : `--since 2026-10-12 --until 2026-10-18`, `--build-only` (reconstruit le site sans rien télécharger), `--cache DOSSIER`, `--no-download`.

Pour voir le site : `python3 -m http.server 8765 --directory site`, puis http://localhost:8765.

## Méthode

Pour chaque paire de pays et chaque semaine, le script mesure dans les événements « racine » de GDELT :

- le nombre d’événements, le ton médiatique moyen et l’échelle de Goldstein moyenne (pondérés par le nombre d’articles) ;
- la part des actes de coopération et de conflit (classes CAMEO 1 à 4) ;
- les recours caractérisés à la force : occupation, armes légères, artillerie, frappes aériennes, violation de cessez-le-feu (codes 192 à 196) et violences de masse (20x). Le code générique 190 est écarté, car trop souvent métaphorique.

La page combine ensuite trois piliers :

- **Diplomatie (35 %)** : ton et Goldstein de la semaine, dès 20 événements. En dessous, estimation structurelle.
- **Économie (25 %)** : commerce estimé par un modèle de gravité, sanctions.
- **Sécurité (40 %)** : alliances et traités, abaissée par les recours caractérisés à la force.

Un plancher « Conflit armé » ou « Hostilité » s’applique quand les recours à la force sont nombreux et le ton négatif. C’est un signal automatique, à confirmer par ACLED ou UCDP.

Les zones de violence sont les lieux (niveau région) où la presse signale des recours caractérisés à la force, entre deux pays ou impliquant un groupe armé non étatique. Les lieux situés aux États-Unis ne sont retenus que pour des groupes armés non étatiques, car GDELT y situe souvent des frappes annoncées depuis Washington.

## Limites connues

- GDELT reflète la couverture médiatique, dominée par la presse anglophone : les pays très suivis produisent plus d’événements.
- GDELT ne fournit pas les titres : la page les déduit de l’adresse des articles quand c’est possible.
- Le modèle structurel (alignements, organisations, traités, sanctions, PIB) repose sur des valeurs saisies à la main dans `src/theater-of-the-world.html`, à vérifier et à sourcer.
- Les zones de violence ne sont pas un décompte de victimes.

## Mise en ligne (GitHub Pages)

1. Créer un dépôt GitHub et y pousser ce dossier.
2. Dans *Settings → Pages*, choisir la source « GitHub Actions ».
3. Lancer une première fois le workflow *Mise à jour quotidienne* (onglet *Actions*, bouton *Run workflow*). Il rattrape les jours manquants puis tourne chaque matin.

## Prochaines sources

- **ACLED** : affrontements géolocalisés et victimes, pour confirmer les conflits armés (compte et clé d’accès nécessaires).
- **OpenSanctions** : remplacer la liste de sanctions saisie à la main.
- **UN Comtrade** : remplacer le modèle de gravité par le commerce bilatéral réel.
- **Votes à l’AGNU** : remplacer l’alignement saisi à la main par la convergence réelle des votes.
