"""
build_stats.py
===============
Lee todos los JSON de data/matches/*.json (generados por scraper.py) y los
agrega en:
  - data/teams.json    -> stats por equipo
  - data/players.json  -> stats por jugador

Requiere positions.json (tú lo editas a mano) con el mapeo
"NOMBRE EXACTO COMO APARECE EN LA ACTA" -> "Portero" | "Defensa" | "Centrocampista" | "Delantero"
Los jugadores que no aparezcan en positions.json se marcan como "Sin definir".

USO:
    python build_stats.py
"""

import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MATCHES_DIR = DATA_DIR / "matches"
POSITIONS_PATH = Path(__file__).parent / "positions.json"

MATCH_LENGTH = 90  # se asume partido completo de 90'; los añadidos de tiempo no vienen en la acta
BUCKETS = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90)]


def bucket_index(minute: int) -> int:
    minute = min(minute, 90)
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo < minute <= hi or (lo == 0 and minute == 0):
            return i
    return len(BUCKETS) - 1


def load_positions():
    if POSITIONS_PATH.exists():
        return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    return {}


def player_minutes(side: dict, match_length=MATCH_LENGTH):
    """
    Devuelve {nombre: (dorsal, minuto_inicio, minuto_fin)} para todos los
    jugadores que llegaron a pisar el campo en ese partido, a partir de
    starters/bench/substitutions de un lado (home o away) del JSON del partido.
    """
    intervals = {}

    starters_by_name = {p["name"]: p["dorsal"] for p in side.get("starters", [])}
    for name, dorsal in starters_by_name.items():
        intervals[name] = [dorsal, 0, match_length]  # por defecto, todo el partido

    # aplica las sustituciones en orden de minuto
    subs = sorted(side.get("substitutions", []), key=lambda s: s["minute"])
    for sub in subs:
        minute = sub["minute"]
        out_p, in_p = sub.get("out"), sub.get("in")
        if out_p and out_p["name"] in intervals:
            intervals[out_p["name"]][2] = minute
        elif out_p:
            # jugador que sale pero no estaba registrado como titular (raro) -> lo ignoramos
            pass
        if in_p:
            if in_p["name"] in intervals:
                # reentra tras haber salido antes (raro, pero por si acaso)
                intervals[in_p["name"]][2] = match_length
            else:
                intervals[in_p["name"]] = [in_p["dorsal"], minute, match_length]

    return {name: tuple(v) for name, v in intervals.items()}


def was_on_pitch(intervals: dict, name: str, minute: int) -> bool:
    if name not in intervals:
        return False
    _, start, end = intervals[name]
    return start <= minute <= end


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
    player_minutes_total = defaultdict(int)
    player_goals_total = defaultdict(int)
    player_goals_conceded_total = defaultdict(int)
    player_dorsal = {}
    player_team = {}
    player_ranges = defaultdict(list)  # nombre -> lista de (start, end) por partido

    for f in match_files:
        match = json.loads(f.read_text(encoding="utf-8"))
        home, away = match["home"], match["away"]
        home_name, away_name = home["name"], away["name"]
        if not home_name or not away_name:
            continue

        team_played[home_name] += 1
        team_played[away_name] += 1

        home_intervals = player_minutes(home)
        away_intervals = player_minutes(away)

        for name, (dorsal, start, end) in home_intervals.items():
            if end <= start:
                continue
            player_matches[name] += 1
            player_minutes_total[name] += (end - start)
            player_dorsal[name] = dorsal
            player_team[name] = home_name
            player_ranges[name].append((start, end))

        for name, (dorsal, start, end) in away_intervals.items():
            if end <= start:
                continue
            player_matches[name] += 1
            player_minutes_total[name] += (end - start)
            player_dorsal[name] = dorsal
            player_team[name] = away_name
            player_ranges[name].append((start, end))

        # goles: hay que decidir de qué equipo es cada gol comparando el
        # autor con las plantillas de cada lado. Si es "own_goal", el gol
        # cuenta A FAVOR del equipo contrario y EN CONTRA del equipo del autor.
        home_names = set(home_intervals.keys())
        away_names = set(away_intervals.keys())

        for goal in match.get("goals", []):
            scorer = goal["scorer"]
            minute = goal["minute"]
            b = bucket_index(minute)
            is_own_goal = goal.get("type") == "own_goal"

            if scorer in home_names:
                scoring_team, conceding_team = (away_name, home_name) if is_own_goal else (home_name, away_name)
            elif scorer in away_names:
                scoring_team, conceding_team = (home_name, away_name) if is_own_goal else (away_name, home_name)
            else:
                # autor no encontrado en ninguna plantilla (nombre distinto entre
                # tabla de goles y alineación); se ignora para las stats de equipo
                continue

            team_gf_buckets[scoring_team][b] += 1
            team_ga_buckets[conceding_team][b] += 1
            team_goals_against_total[conceding_team] += 1

            if not is_own_goal:
                player_goals_total[scorer] += 1

            # goles encajados por el portero que estuviera en el campo en ese minuto
            conceding_side_intervals = home_intervals if conceding_team == home_name else away_intervals
            for name, (dorsal, start, end) in conceding_side_intervals.items():
                if positions.get(name) == "Portero" and start <= minute <= end:
                    player_goals_conceded_total[name] += 1

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
    for name, matches in player_matches.items():
        minutes_total = player_minutes_total[name]
        ranges = player_ranges[name]
        avg_start = round(sum(r[0] for r in ranges) / len(ranges)) if ranges else 0
        avg_end = round(sum(r[1] for r in ranges) / len(ranges)) if ranges else 0
        position = positions.get(name, "Sin definir")
        entry = {
            "name": name,
            "dorsal": player_dorsal.get(name),
            "team": player_team.get(name),
            "position": position,
            "matches": matches,
            "minutesTotal": minutes_total,
            "minutesAvg": round(minutes_total / matches, 1) if matches else 0,
            "rangeStart": avg_start,
            "rangeEnd": avg_end,
            "goalsTotal": player_goals_total.get(name, 0),
            "goalsAvg": round(player_goals_total.get(name, 0) / matches, 2) if matches else 0,
        }
        if position == "Portero":
            gc = player_goals_conceded_total.get(name, 0)
            entry["goalsConcededTotal"] = gc
            entry["goalsConcededAvg"] = round(gc / matches, 2) if matches else 0
        else:
            entry["goalsConcededTotal"] = None
            entry["goalsConcededAvg"] = None
        players_out[name] = entry

    (DATA_DIR / "teams.json").write_text(
        json.dumps(teams_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA_DIR / "players.json").write_text(
        json.dumps(players_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OK: {len(teams_out)} equipos, {len(players_out)} jugadores.")

    missing = [n for n in players_out if players_out[n]["position"] == "Sin definir"]
    if missing:
        print(f"\nAviso: {len(missing)} jugadores sin posición asignada en positions.json.")
        print("(la web los mostrará igualmente, solo que sin ese dato)")


if __name__ == "__main__":
    main()
