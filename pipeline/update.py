#!/usr/bin/env python3
"""Theater of the World : collecte quotidienne des événements GDELT et construction des données du site.

Chaque jour, GDELT publie vers 07:00 UTC un fichier des événements de la veille.
Ce script :
  1. télécharge les fichiers manquants (cache local, jamais versionné) ;
  2. agrège chaque jour par paire de pays et par lieu de violence -> data/days/AAAA-MM-JJ.json.gz ;
  3. regroupe les jours en semaines ISO -> data/weeks/AAAA-Www.json ;
  4. écrit site/data/latest.json (12 dernières semaines) et site/index.html.

Le calcul des notes (diplomatie, économie, sécurité) reste dans la page : ce script ne fait que mesurer.

Usage :
  python3 -I pipeline/update.py                          # jours manquants jusqu’à hier
  python3 -I pipeline/update.py --since 2026-10-12 --until 2026-10-18
  python3 -I pipeline/update.py --build-only             # reconstruit le site depuis data/
Options : --cache DOSSIER (fichiers bruts), --no-download
"""
import argparse
import datetime as dt
import gzip
import io
import json
import math
import os
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS = os.path.join(ROOT, 'data', 'days')
WEEKS = os.path.join(ROOT, 'data', 'weeks')
SITE = os.path.join(ROOT, 'site')
PAGE = os.path.join(ROOT, 'src', 'theater-of-the-world.html')
URL = 'https://data.gdeltproject.org/events/{}.export.CSV.zip'

N_WEEKS = 12          # profondeur de la frise
DOC_MIN = 20          # événements par semaine pour qu’une relation soit « documentée »
MAX_GEO = 20          # zones de violence publiées
GEO_MIN = 6           # événements dans la semaine pour qu’une zone soit publiée
STALE_DAYS = 7        # on ignore les événements datés de plus d’une semaine avant leur publication

# Codes CAMEO qui diffèrent de l’ISO 3166 alpha-3, et codes régionaux à ignorer.
FIX = {'TMP': 'TLS', 'ROM': 'ROU', 'ZAR': 'COD', 'KOS': 'XKX'}
REGIONS = set('AFR ASA BLK CRB CAU CFR CAS CEU EIN EAF EEU EUR LAM MEA MDT NAF NMR PGS SCN SAM SAS SEA SAF WAF WST'.split())

# Colonnes du fichier d’export GDELT 1.0 (58 colonnes).
SQLDATE, A1NAME, A1CTRY, A1TYPE, A2NAME, A2CTRY, A2TYPE = 1, 6, 7, 12, 16, 17, 22
ISROOT, CODE, ROOTCODE, QUAD, GOLD, ARTICLES, TONE = 25, 26, 28, 29, 30, 33, 34
GEO_TYPE, GEO_NAME, GEO_ADM1, GEO_LAT, GEO_LON, SRCURL = 49, 50, 52, 53, 54, 57
# Recours à la force « caractérisé » : occupation, armes légères, artillerie, frappes aériennes,
# violation de cessez-le-feu (192 à 196) et violences de masse (20x). Le code générique 190 est
# trop souvent métaphorique (« guerre commerciale ») pour être retenu seul.
MILITARY = ('192', '193', '194', '195', '196')
# Pour situer la violence, il faut en plus deux pays différents ou un groupe armé non étatique :
# sans ce filtre, les faits divers et l’activité militaire intérieure dominent la carte.
ARMED = {'REB', 'INS', 'SEP'}  # « UAF » (forces armées non identifiées) capte surtout des fusillades


def log(*a):
    print(*a, file=sys.stderr)


def day_path(d):
    return os.path.join(DAYS, d.isoformat() + '.json.gz')


def week_id(d):
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'


def week_monday(wid):
    y, w = wid.split('-W')
    return dt.date.fromisocalendar(int(y), int(w), 1)


def fetch(d, cache, allow):
    path = os.path.join(cache, d.strftime('%Y%m%d') + '.export.CSV.zip')
    if os.path.exists(path):
        return path
    if not allow:
        log(f'  {d} : absent du cache, téléchargement désactivé')
        return None
    url = URL.format(d.strftime('%Y%m%d'))
    log(f'  téléchargement {url}')
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(path + '.part', 'wb') as f:
            f.write(r.read())
    except Exception as e:  # fichier pas encore publié, réseau…
        log(f'  {d} : indisponible ({e})')
        return None
    os.replace(path + '.part', path)
    return path


def parse_day(path, d):
    """Agrège un fichier quotidien : paires de pays, meilleurs articles, lieux de violence."""
    pairs = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0])  # n, poids, Σgoldstein, Σton, q1..q4, n recours caractérisé à la force
    events = defaultdict(list)
    geo = {}
    rows = kept = 0
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as fh:
        for line in io.TextIOWrapper(fh, encoding='utf-8', errors='replace'):
            r = line.rstrip('\n').split('\t')
            if len(r) < 58:
                continue
            rows += 1
            try:
                ed = dt.date(int(r[SQLDATE][:4]), int(r[SQLDATE][4:6]), int(r[SQLDATE][6:8]))
            except ValueError:
                continue
            if not 0 <= (d - ed).days <= STALE_DAYS or r[ISROOT] != '1':
                continue
            kept += 1
            root = r[ROOTCODE]
            a, b = FIX.get(r[A1CTRY], r[A1CTRY]), FIX.get(r[A2CTRY], r[A2CTRY])
            military = r[CODE][:3] in MILITARY or root == '20'
            international = len(a) == 3 and len(b) == 3 and a != b
            nonstate = r[A1TYPE] in ARMED or r[A2TYPE] in ARMED
            # Types 2 et 3 = lieux américains : GDELT y situe souvent des frappes annoncées à Washington.
            if military and r[GEO_ADM1] and (nonstate and r[GEO_TYPE] in ('2', '3', '4', '5')
                                             or international and r[GEO_TYPE] in ('4', '5')):
                try:
                    lat, lon = float(r[GEO_LAT]), float(r[GEO_LON])
                except ValueError:
                    lat = None
                if lat is not None:
                    g = geo.setdefault(r[GEO_ADM1], [0, 0.0, 0.0, Counter(), []])
                    g[0] += 1; g[1] += lat; g[2] += lon; g[3][r[GEO_NAME]] += 1
                    g[4].append((int(r[ARTICLES] or 0), r[SRCURL], ed.isoformat(), r[CODE], r[A1NAME], r[A2NAME]))
            if len(a) != 3 or len(b) != 3 or a == b or a in REGIONS or b in REGIONS:
                continue
            k = '|'.join(sorted((a, b)))
            arts = int(r[ARTICLES] or 0)
            w = math.log1p(arts) + 1
            p = pairs[k]
            p[0] += 1; p[1] += w
            p[2] += w * float(r[GOLD] or 0); p[3] += w * float(r[TONE] or 0)
            q = int(r[QUAD] or 1)
            if 1 <= q <= 4:
                p[3 + q] += w
            if military:
                p[8] += 1
            events[k].append((arts, r[SRCURL], ed.isoformat(), root, r[CODE], r[A1NAME], r[A2NAME], a, b))
    out_pairs = {k: [v[0], round(v[1], 2), round(v[2], 2), round(v[3], 2)] + [round(x, 2) for x in v[4:8]] + [v[8]]
                 for k, v in pairs.items() if v[0] >= 2}
    out_events = {k: top_events(v, 3) for k, v in events.items() if k in out_pairs and out_pairs[k][0] >= 3}
    out_geo = {k: [g[0], round(g[1], 3), round(g[2], 3), g[3].most_common(1)[0][0], [list(e) for e in top_events(g[4], 2)]]
               for k, g in geo.items() if g[0] >= 2}
    return {'date': d.isoformat(), 'rows': rows, 'kept': kept, 'pairs': out_pairs, 'events': out_events, 'geo': out_geo}


def top_events(evs, n):
    """Les n événements les plus couverts, une seule fois par article."""
    seen, out = set(), []
    for e in sorted(evs, key=lambda e: -e[0]):
        if e[1] in seen:
            continue
        seen.add(e[1]); out.append(list(e))
        if len(out) == n:
            break
    return out


def build_week(wid):
    mon = week_monday(wid)
    pairs = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0])
    events, geo = defaultdict(list), {}
    days, rows = [], 0
    for i in range(7):
        p = day_path(mon + dt.timedelta(days=i))
        if not os.path.exists(p):
            continue
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            day = json.load(f)
        days.append(day['date']); rows += day['kept']
        for k, v in day['pairs'].items():
            acc = pairs[k]
            for j in range(9):
                acc[j] += v[j]
        for k, v in day['events'].items():
            events[k].extend(v)
        for k, v in day['geo'].items():
            g = geo.setdefault(k, [0, 0.0, 0.0, Counter(), []])
            g[0] += v[0]; g[1] += v[1]; g[2] += v[2]; g[3][v[3]] += v[0]; g[4].extend(v[4])
    week = {
        'id': wid, 'start': mon.isoformat(), 'end': (mon + dt.timedelta(days=6)).isoformat(), 'days': days, 'events': rows,
        'pairs': {k: [v[0], round(v[1], 2), round(v[2], 2), round(v[3], 2)] + [round(x, 2) for x in v[4:8]] + [v[8]] for k, v in pairs.items()},
        'top': {k: top_events(v, 6) for k, v in events.items() if pairs[k][0] >= 10},
        'geo': {k: [g[0], round(g[1], 3), round(g[2], 3), g[3].most_common(1)[0][0], top_events(g[4], 3)] for k, g in geo.items()},
    }
    os.makedirs(WEEKS, exist_ok=True)
    with open(os.path.join(WEEKS, wid + '.json'), 'w', encoding='utf-8') as f:
        json.dump(week, f, ensure_ascii=False, separators=(',', ':'))
    return week


def stats(v):
    """[n, Goldstein moyen, ton moyen, part coopération verbale, matérielle, conflit verbal, matériel, n force, part force]."""
    n, w = v[0], v[1] or 1
    return [n, round(v[2] / w, 2), round(v[3] / w, 2)] + [round(x / w, 3) for x in v[4:8]] + [v[8], round(v[8] / n, 3) if n else 0]


def build_site():
    ids = sorted(f[:-5] for f in os.listdir(WEEKS) if f.endswith('.json')) if os.path.isdir(WEEKS) else []
    if not ids:
        log('aucune semaine agrégée')
        return
    # Semaines consécutives jusqu’à la plus récente, même si une semaine manque.
    last = week_monday(ids[-1])
    span = [week_id(last - dt.timedelta(weeks=i)) for i in range(N_WEEKS - 1, -1, -1)]
    span = [w for w in span if w >= ids[0]]
    weeks = []
    for wid in span:
        p = os.path.join(WEEKS, wid + '.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                weeks.append(json.load(f))
        else:
            mon = week_monday(wid)
            weeks.append({'id': wid, 'start': mon.isoformat(), 'end': (mon + dt.timedelta(days=6)).isoformat(), 'days': [], 'events': 0, 'pairs': {}, 'top': {}, 'geo': {}})

    documented = sorted({k for w in weeks for k, v in w['pairs'].items() if v[0] >= DOC_MIN})
    pairs = []
    for k in documented:
        a, b = k.split('|')
        st = [stats(w['pairs'][k]) if k in w['pairs'] and w['pairs'][k][0] >= 5 else None for w in weeks]
        ev = [[i] + e for i, w in enumerate(weeks) for e in w['top'].get(k, [])[:4]]
        pairs.append({'a': a, 'b': b, 'st': st, 'ev': ev})

    latest = weeks[-1]['geo']
    keys = sorted((k for k in latest if latest[k][0] >= GEO_MIN), key=lambda k: -latest[k][0])[:MAX_GEO]
    geo = []
    for k in keys:
        g = latest[k]
        geo.append({'k': k, 'name': g[3], 'll': [round(g[2] / g[0], 3), round(g[1] / g[0], 3)],
                    'wk': [w['geo'].get(k, [0])[0] for w in weeks], 'ev': g[4]})

    data = {
        'generated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': 'GDELT 1.0 Event Database (data.gdeltproject.org/events)',
        'docMin': DOC_MIN,
        'weeks': [{'id': w['id'], 'start': w['start'], 'end': w['end'], 'days': len(w['days']), 'last': (w['days'] or [None])[-1], 'events': w['events']} for w in weeks],
        'pairs': pairs,
        'geo': geo,
    }
    os.makedirs(os.path.join(SITE, 'data'), exist_ok=True)
    with open(os.path.join(SITE, 'data', 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    with open(PAGE, encoding='utf-8') as f:
        page = f.read()
    with open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
                '<style>:root{padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}[hidden]{display:none!important}</style>\n'
                '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    log(f'site : {len(weeks)} semaines, {len(pairs)} relations documentées, {len(geo)} zones de violence')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', type=dt.date.fromisoformat)
    ap.add_argument('--until', type=dt.date.fromisoformat)
    ap.add_argument('--cache', default=os.path.join(ROOT, '.cache', 'gdelt'))
    ap.add_argument('--no-download', action='store_true')
    ap.add_argument('--build-only', action='store_true')
    args = ap.parse_args()

    if not args.build_only:
        yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
        until = args.until or yesterday
        if args.since:
            since = args.since
        else:
            done = sorted(f[:10] for f in os.listdir(DAYS)) if os.path.isdir(DAYS) else []
            since = dt.date.fromisoformat(done[-1]) + dt.timedelta(days=1) if done else until - dt.timedelta(days=6)
        os.makedirs(args.cache, exist_ok=True)
        os.makedirs(DAYS, exist_ok=True)
        touched = set()
        d = since
        while d <= until:
            path = fetch(d, args.cache, not args.no_download)
            if path:
                day = parse_day(path, d)
                with gzip.open(day_path(d), 'wt', encoding='utf-8') as f:
                    json.dump(day, f, ensure_ascii=False, separators=(',', ':'))
                log(f'  {d} : {day["kept"]} événements retenus, {len(day["pairs"])} paires')
                touched.add(week_id(d))
            d += dt.timedelta(days=1)
        for wid in sorted(touched):
            build_week(wid)
    build_site()


if __name__ == '__main__':
    main()
