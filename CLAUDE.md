# CLAUDE.md

Les consignes communes à tous les agents sont dans AGENTS.md, importé ici :

@AGENTS.md

## Spécifique à Claude Code

- Aperçu du site : la configuration `theater` de `.claude/launch.json` sert `site/` sur le port 8766. Lancer `python3 -I pipeline/update.py --build-only` avant, pour que `site/` reflète `src/`.
- Vérifier une modification de la page dans le navigateur intégré (carte affichée, panneau d’une relation, frise, console sans erreur), à la largeur bureau puis mobile.
- `src/theater-of-the-world.html` est long : le lire par plages (`offset`/`limit`) ou chercher une fonction avec `grep -n` plutôt que de tout charger. Les fichiers de `data/` et `site/data/latest.json` sont volumineux : n’en lire que le début (`head -c`, `gunzip -c … | head -c`).
- Ne pas lancer de téléchargement GDELT sans accord : préférer `--build-only` ou `--no-download`.
