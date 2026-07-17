"""
build_stats.py
===============
Lee todos los JSON de data/matches/*.json (generados por scraper.py) y los
agrega en:
  - site/data/teams.json    -> stats por equipo
  - site/data/players.json  -> stats por jugador

Se escriben dentro de site/ (y no en data/) a propósito: GitHub Pages solo
publica el contenido de la carpeta site/, así que los JSON que necesita leer
el navegador tienen que vivir ahí. data/matches/ se queda como el archivo
"crudo" de cada partido (no hace falta publicarlo).

IDENTIDAD DE JUGADOR: cada jugador se identifica por su ID único de la FCF
(el número al final de la URL de su perfil, p.ej. ".../jugador/.../628037"),
no por el texto de su nombre. Esto es a propósito: dos hermanos u otras
personas con el mismo nombre completo NUNCA se pueden confundir entre sí,
aunque el texto de la acta sea idéntico letra por letra. Si algún jugador
raro no trajera ID (no debería pasar, pero por si acaso), se usa su nombre
normalizado como respaldo.

Requiere positions.json (tú lo editas a mano) con el mapeo
"NOMBRE EXACTO COMO APARECE EN LA ACTA" -> "Portero" | "Defensa" | "Centrocampista" | "Delantero"
Los jugadores que no aparezcan en positions.json se marcan como "Sin definir".
Como positions.json lo editas tú a mano, sigue funcionando por nombre (no por
ID) — si dos hermanos con el mismo nombre completo juegan en el mismo grupo,
avísame y lo resolvemos aparte (sería un caso muy raro).

USO:
    python build_stats.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MATCHES_DIR = DATA_DIR / "matches"
POSITIONS_PATH = Path(__file__).parent / "positions.json"
SITE_DATA_DIR = Path(__file__).parent / "site" / "data"
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

MATCH_LENGTH = 90  # se asume partido completo de 90'; los añadidos de tiempo no vienen en la acta
BUCKETS = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90)]

# Si se rellena con un trozo de nombre (en mayúsculas, tal como aparece en la
# acta), se imprime por consola, partido a partido, todo lo que se encuentre
# sobre cualquier jugador cuyo nombre normalizado contenga ese texto: en qué
# partido, con qué ID, si es titular o suplente, y qué minutos se le
# calculan. Útil para verificar casos como dos hermanos con el mismo
# apellido, y confirmar que sus datos no se mezclan.
DEBUG_PLAYER_NAME_FILTER = "FELEZ NAVARRO"  # ejemplo: "FELEZ NAVARRO"


def normalize_name(name):
    """
    Colapsa cualquier tipo de espacio (incluido el NBSP \\xa0, que se ve
    idéntico a un espacio normal pero es un carácter distinto) en un único
    espacio normal, y quita espacios sobrantes al principio/final.
    """
    if name is None:
        return name
    return re.sub(r"\s+", " ", name).strip()


def player_key(player_id, name):
    """
    Clave interna para identificar a un jugador de forma inequívoca: su ID
    único de la FCF si está disponible (caso normal), o su nombre
    normalizado como respaldo si por lo que sea faltara el ID.
    """
    if player_id:
        return f"id:{player_id}"
    return f"noid:{normalize_name(name)}"


def bucket_index(minute: int) -> int:
    minute = min(minute, 90)
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo < minute <= hi or (lo == 0 and minute == 0):
            return i
    return len(BUCKETS) - 1


def load_positions():
    if not POSITIONS_PATH.exists():
        return {}
    raw = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    return {normalize_name(k): v for k, v in raw.items()}


def roster_keys(side: dict) -> set:
    """
    Reúne las claves de TODOS los jugadores mencionados para un lado del
    partido — titulares, suplentes, y quien salga/entre en las
    sustituciones — sin depender de que el cálculo de minutos esté afinado.
    Se usa para decidir de qué equipo es cada gol.
    """
    keys = set()
    for p in side.get("starters", []) + side.get("bench", []):
        keys.add(player_key(p.get("player_id"), p["name"]))
    for sub in side.get("substitutions", []):
        if sub.get("out"):
            keys.add(player_key(sub["out"].get("player_id"), sub["out"]["name"]))
        if sub.get("in"):
            keys.add(player_key(sub["in"].get("player_id"), sub["in"]["name"]))
    return keys


def player_minutes(side: dict, match_length=MATCH_LENGTH):
    """
    Devuelve {clave_jugador: (dorsal, nombre, minuto_inicio, minuto_fin)}
    para todos los jugadores que llegaron a pisar el campo en ese partido.
    """
    intervals = {}

    for p in side.get("starters", []):
        key = player_key(p.get("player_id"), p["name"])
        intervals[key] = [p["dorsal"], normalize_name(p["name"]), 0, match_length]

    # aplica las sustituciones en orden de minuto
    subs = sorted(side.get("substitutions", []), key=lambda s: s["minute"])
    for sub in subs:
        minute = sub["minute"]
        out_p, in_p = sub.get("out"), sub.get("in")
        if out_p:
            out_key = player_key(out_p.get("player_id"), out_p["name"])
            if out_key in intervals:
                intervals[out_key][3] = minute
            # si sale alguien que no estaba registrado como titular (raro), se ignora
        if in_p:
            in_key = player_key(in_p.get("player_id"), in_p["name"])
            if in_key in intervals:
                # reentra tras haber salido antes (raro, pero por si acaso)
                intervals[in_key][3] = match_length
            else:
                intervals[in_key] = [in_p["dorsal"], normalize_name(in_p["name"]), minute, match_length]

    return {key: tuple(v) for key, v in intervals.items()}


def main():
    positions = load_positions()
    match_files = sorted(MATCHES_DIR.glob("*.json"))
    if not match_files:
        print("No hay partidos en data/matches/. Ejecuta antes scraper.py")
        return

    # acumuladores
    team_played = defaultdict(int)
    team_goals_against_total = defaultdict(int)
    team_gf_buckets = defaultdict(lambda: [0] * 6)
    team_ga_buckets = defaultdict(lambda: [0] * 6)

    player_matches = defaultdict(int)
    player_call_ups = defaultdict(int)
    player_titular = defaultdict(int)
    player_minutes_total = defaultdict(int)
    player_goals_total = defaultdict(int)
    player_goals_conceded_total = defaultdict(int)
    player_dorsal = {}
    player_team = {}
    player_name = {}  # clave -> nombre normalizado, para mostrar en la web

    goals_total_seen = 0
    goals_skipped = 0
    subs_total_seen = 0
    matches_with_zero_subs = 0

    debug_filter = DEBUG_PLAYER_NAME_FILTER.strip().upper()

    for f in match_files:
        match = json.loads(f.read_text(encoding="utf-8"))
        home, away = match["home"], match["away"]
        home_name, away_name = home["name"], away["name"]
        if not home_name or not away_name:
            continue

        n_subs_this_match = len(home.get("substitutions", [])) + len(away.get("substitutions", []))
        subs_total_seen += n_subs_this_match
        if n_subs_this_match == 0:
            matches_with_zero_subs += 1

        team_played[home_name] += 1
        team_played[away_name] += 1

        home_intervals = player_minutes(home)
        away_intervals = player_minutes(away)

        for key, (dorsal, name, start, end) in home_intervals.items():
            player_name.setdefault(key, name)
            if debug_filter and debug_filter in name.upper():
                print(f"    [debug-jugador] {f.name}: {name} ({key}) en {home_name} -> "
                      f"minutos {start}-{end}{' (NO CUENTA, end<=start)' if end <= start else ''}")
            if end <= start:
                continue
            player_matches[key] += 1
            player_minutes_total[key] += (end - start)
            player_dorsal[key] = dorsal
            player_team[key] = home_name

        for key, (dorsal, name, start, end) in away_intervals.items():
            player_name.setdefault(key, name)
            if debug_filter and debug_filter in name.upper():
                print(f"    [debug-jugador] {f.name}: {name} ({key}) en {away_name} -> "
                      f"minutos {start}-{end}{' (NO CUENTA, end<=start)' if end <= start else ''}")
            if end <= start:
                continue
            player_matches[key] += 1
            player_minutes_total[key] += (end - start)
            player_dorsal[key] = dorsal
            player_team[key] = away_name

        # Convocatorias: cualquiera que aparezca en Titulars o Suplents de
        # ese partido cuenta como convocado, haya llegado a jugar o no.
        # "Titular" y "Suplente" son categorías que se excluyen entre sí y
        # suman el total de convocatorias: titular = empezó el partido en el
        # once inicial; suplente = empezó en el banquillo, haya llegado a
        # jugar o no.
        for side_name, side in ((home_name, home), (away_name, away)):
            for p in side.get("starters", []):
                key = player_key(p.get("player_id"), p["name"])
                name = normalize_name(p["name"])
                player_name.setdefault(key, name)
                player_call_ups[key] += 1
                player_titular[key] += 1
                player_dorsal.setdefault(key, p["dorsal"])
                player_team.setdefault(key, side_name)
                if debug_filter and debug_filter in name.upper():
                    print(f"    [debug-jugador] {f.name}: {name} ({key}) TITULAR en {side_name}")
            for p in side.get("bench", []):
                key = player_key(p.get("player_id"), p["name"])
                name = normalize_name(p["name"])
                player_name.setdefault(key, name)
                player_call_ups[key] += 1
                player_dorsal.setdefault(key, p["dorsal"])
                player_team.setdefault(key, side_name)
                if debug_filter and debug_filter in name.upper():
                    print(f"    [debug-jugador] {f.name}: {name} ({key}) SUPLENTE en {side_name}")

        # goles: hay que decidir de qué equipo es cada gol comparando el
        # autor con las plantillas de cada lado, usando su ID de jugador
        # (con respaldo por nombre si faltara el ID). Si es "own_goal", el
        # gol cuenta A FAVOR del equipo contrario y EN CONTRA del autor.
        home_keys = roster_keys(home)
        away_keys = roster_keys(away)

        for goal in match.get("goals", []):
            scorer_name = normalize_name(goal["scorer"])
            scorer_key = player_key(goal.get("scorer_id"), goal["scorer"])
            minute = goal["minute"]
            b = bucket_index(minute)
            is_own_goal = goal.get("type") == "own_goal"
            goals_total_seen += 1

            if scorer_key in home_keys:
                scoring_team, conceding_team = (away_name, home_name) if is_own_goal else (home_name, away_name)
            elif scorer_key in away_keys:
                scoring_team, conceding_team = (home_name, away_name) if is_own_goal else (away_name, home_name)
            else:
                # autor no encontrado en ninguna plantilla; se ignora para las stats de equipo
                goals_skipped += 1
                print(f"  AVISO: gol de '{scorer_name}' (min {minute}) en {home_name} vs {away_name} "
                      f"no coincide con ningún jugador de la alineación de ese partido — se descarta.")
                continue

            team_gf_buckets[scoring_team][b] += 1
            team_ga_buckets[conceding_team][b] += 1
            team_goals_against_total[conceding_team] += 1

            if not is_own_goal:
                player_goals_total[scorer_key] += 1
                player_name.setdefault(scorer_key, scorer_name)

            # goles encajados por el portero que estuviera en el campo en ese minuto
            conceding_side_intervals = home_intervals if conceding_team == home_name else away_intervals
            for key, (dorsal, name, start, end) in conceding_side_intervals.items():
                if positions.get(name) == "Portero" and start <= minute <= end:
                    player_goals_conceded_total[key] += 1

    # -------- construir teams.json --------
    teams_out = {}
    for team, played in team_played.items():
        teams_out[team] = {
            "name": team,
            "matchesPlayed": played,
            "goalsAgainstTotal": team_goals_against_total[team],
            "goalsAgainstAvg": round(team_goals_against_total[team] / played, 2),
            "gfBucketsTotal": team_gf_buckets[team],
            "gfBucketsAvg": [round(v / played, 2) for v in team_gf_buckets[team]],
            "gaBucketsTotal": team_ga_buckets[team],
            "gaBucketsAvg": [round(v / played, 2) for v in team_ga_buckets[team]],
        }

    # -------- construir players.json --------
    players_out = {}
    all_keys = set(player_matches.keys()) | set(player_call_ups.keys())
    for key in all_keys:
        name = player_name.get(key, "(nombre desconocido)")
        matches = player_matches.get(key, 0)
        call_ups = player_call_ups.get(key, 0)
        titular = player_titular.get(key, 0)
        suplente = call_ups - titular
        minutes_total = player_minutes_total[key]
        position = positions.get(name, "Sin definir")
        entry = {
            "name": name,
            "dorsal": player_dorsal.get(key),
            "team": player_team.get(key),
            "position": position,
            "callUpsTotal": call_ups,
            "titularTotal": titular,
            "suplenteTotal": suplente,
            "matches": matches,
            "minutesTotal": minutes_total,
            "minutesAvg": round(minutes_total / matches, 1) if matches else 0,
            "goalsTotal": player_goals_total.get(key, 0),
            "goalsAvg": round(player_goals_total.get(key, 0) / matches, 2) if matches else 0,
        }
        if position == "Portero":
            gc = player_goals_conceded_total.get(key, 0)
            entry["goalsConcededTotal"] = gc
            entry["goalsConcededAvg"] = round(gc / matches, 2) if matches else 0
        else:
            entry["goalsConcededTotal"] = None
            entry["goalsConcededAvg"] = None
        players_out[key] = entry

    (SITE_DATA_DIR / "teams.json").write_text(
        json.dumps(teams_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (SITE_DATA_DIR / "players.json").write_text(
        json.dumps(players_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OK: {len(teams_out)} equipos, {len(players_out)} jugadores.")
    print(f"Goles procesados: {goals_total_seen - goals_skipped} / {goals_total_seen} "
          f"({goals_skipped} descartados por no encontrar al autor en la alineación)")
    print(f"Sustituciones detectadas: {subs_total_seen} en {len(match_files)} partidos "
          f"({subs_total_seen / len(match_files):.1f} de media por partido). "
          f"Partidos con 0 sustituciones detectadas: {matches_with_zero_subs} "
          f"(sospechoso si es un número alto — en fútbol amateur casi siempre hay alguna).")

    missing = [k for k in players_out if players_out[k]["position"] == "Sin definir"]
    if missing:
        print(f"\nAviso: {len(missing)} jugadores sin posición asignada en positions.json.")
        print("(la web los mostrará igualmente, solo que sin ese dato)")


if __name__ == "__main__":
    main()
