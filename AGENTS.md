# AGENTS.md — Theater of the World

Consignes pour les agents de code (Claude Code, Codex, Cursor…) qui travaillent dans ce dépôt. Le contexte général, la méthode et les limites sont dans le [README](README.md) : le lire avant toute modification de fond.

## En bref

Carte du monde des relations bilatérales, notées de −10 (conflit armé) à +10 (alliance), mise à jour chaque matin à partir des événements GDELT 1.0. Deux pièces seulement :

- `pipeline/update.py` **mesure** : téléchargement GDELT → agrégats quotidiens → agrégats hebdomadaires → `site/data/latest.json` et `site/index.html`.
- `src/theater-of-the-world.html` **note et affiche** : modèle structurel, calcul des trois piliers, carte, panneaux, frise.

Ne pas déplacer le calcul des notes dans le script : le partage « le script mesure, la page note » est voulu.

## Commandes

```bash
python3 -I pipeline/update.py                  # jours manquants jusqu’à hier, puis reconstruction du site
python3 -I pipeline/update.py --build-only     # reconstruit site/ depuis data/, sans réseau (le plus courant en dev)
python3 -I pipeline/update.py --since 2026-10-12 --until 2026-10-18 --no-download
python3 -m http.server 8766 --directory site   # voir le site : http://localhost:8766
```

- Toujours lancer Python avec `-I`.
- Un jour GDELT pèse environ 8 Mo : ne pas lancer de téléchargement massif sans raison. Les fichiers bruts vont dans `.cache/gdelt/` (ignoré par git).
- Il n’y a ni tests ni linter. Vérifier une modification en lançant `--build-only`, puis en ouvrant la page et en lisant la console du navigateur.

## Organisation des fichiers

| Chemin | Versionné | Remarques |
|---|---|---|
| `src/theater-of-the-world.html` | oui | **Fragment** HTML (pas de `<!doctype>`, `<head>` ni `<body>`) : `build_site()` l’enveloppe. Ne pas ajouter de squelette. |
| `pipeline/update.py` | oui | Python standard uniquement, aucune dépendance. |
| `data/days/AAAA-MM-JJ.json.gz` | oui | Écrit par le bot chaque matin. |
| `data/weeks/AAAA-Www.json` | oui | Recalculé à partir des jours. |
| `site/` | non | Généré. Ne jamais éditer à la main : modifier `src/` puis reconstruire. |
| `.github/workflows/daily.yml` | oui | Cron 07:30 UTC, commit des données, déploiement GitHub Pages. |

## Règles de travail

### Pipeline (`pipeline/update.py`)

- Rester en bibliothèque standard : le workflow n’installe rien.
- Les tableaux sont positionnels pour garder les fichiers compacts. Toute modification de forme doit être répercutée partout où ils sont lus :
  - paire (jour et semaine) : `[n, poids, Σgoldstein, Σton, q1, q2, q3, q4, n_force]` ;
  - `stats()` → `st` dans `latest.json` : `[n, goldstein, ton, part q1, q2, q3, q4, n_force, part_force]`, lu par `liveScore()` dans la page (`st[7]`, `st[8]`…).
- Changer un seuil (`DOC_MIN`, `GEO_MIN`, filtres `MILITARY`, `ARMED`, `STALE_DAYS`…) modifie la méthode : mettre à jour la section « Méthode » du README dans le même changement.
- Les agrégats déjà versionnés dans `data/` ne se recalculent pas sans les fichiers bruts. Un changement dans `parse_day()` ne s’applique qu’aux nouveaux jours, sauf à retélécharger : le signaler plutôt que de le faire d’office.

### Page (`src/theater-of-the-world.html`)

- Fichier unique d’environ 1 800 lignes : CSS en tête, puis un seul `<script>` avec `startTheater(LIVE)`. Sans `data/latest.json`, la page tourne sur un jeu d’exemple intégré (`LIVE` nul) : les deux modes doivent continuer à fonctionner.
- Bibliothèques externes chargées depuis des CDN à version fixe (d3 7.8.5, topojson-client 3.1.0, datamaps 0.5.9). Ne pas ajouter d’outil de build ni de dépendance npm.
- Les valeurs structurelles (`ORGS`, `TREATY`, `SANCT_*`, alignements, PIB…) sont saisies à la main. Toute nouvelle valeur doit être plausible et, si possible, sourcée dans un commentaire ; ne jamais inventer de chiffres présentés comme réels.
- Pondération des piliers : diplomatie 35 %, économie 25 %, sécurité 40 % (`liveScore()`). Si on la change, mettre le README à jour.
- Garder l’identité visuelle : jetons de couleur sur `:root` (`--s-3` à `--s3` pour l’échelle des relations), polices Archivo et IBM Plex Mono, fond graphite, pas d’effets lumineux. Mise en page utilisable sur mobile.
- Codes pays : ISO 3166 alpha-3 (la table `FIX` du script convertit les codes CAMEO divergents).

### Langue et style

- Interface, commentaires, messages de log, README et messages de commit sont **en français**, avec la typographie française (apostrophe ’, guillemets « », espace avant `:`).
- Respecter le style existant : code compact, commentaires courts qui expliquent le *pourquoi*.

### Git

- Branche principale `main`. Le bot `theater-of-the-world-bot` y pousse chaque jour un commit « Données GDELT au AAAA-MM-JJ » : faire `git pull --rebase` avant de pousser, et ne pas réécrire ces commits.
- Ne pas committer `site/`, `.cache/`, `.claude/` ni `.DS_Store` (déjà dans `.gitignore`).
- Éviter de committer à la main des fichiers de `data/` produits en local, sauf demande explicite : c’est le rôle du workflow, et cela crée des conflits avec le bot.

## Pistes ouvertes

Sources prévues (voir README) : ACLED pour confirmer les conflits, OpenSanctions pour les sanctions, UN Comtrade pour le commerce réel, votes à l’AGNU pour les alignements. Chacune doit remplacer une valeur saisie à la main, pas s’y ajouter.
