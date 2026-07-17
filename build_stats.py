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

Requiere positions.json (tú lo editas a mano) con el mapeo
"NOMBRE EXACTO COMO APARECE EN LA ACTA" -> "Portero" | "Defensa" | "Centrocampista" | "Delantero"
Los jugadores que no aparezcan en positions.json se marcan como "Sin definir".

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


def normalize_name(name):
    """
    Colapsa cualquier tipo de espacio (incluido el NBSP \\xa0, que se ve
    idéntico a un espacio normal pero es un carácter distinto) en un único
    espacio normal, y quita espacios sobrantes al principio/final.
    Sin esto, "DE SOKOLOW LEYVA, BRYAN" (con espacio normal en la tabla de
    alineación) y "DE SOKOLOW LEYVA,\\xa0BRYAN" (con NBSP en la tabla de
    goles, o viceversa) se tratan como dos jugadores distintos y el gol se
    descarta por "no encontrado" — era justo el motivo de que ~80% de los
    goles de la temporada se estuvieran perdiendo.
    """
    if name is None:
        return name
    return re.sub(r"\s+", " ", name).strip()


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


def roster_names(side: dict) -> set:
    """
    Reúne TODOS los nombres mencionados para un lado del partido —
    titulares, suplentes, y quien salga/entre en las sustituciones — sin
    depender de que el cálculo de minutos (que sí depende de que las
    sustituciones estén bien parseadas) esté afinado. Se usa solo para
    decidir de qué equipo es cada gol; el cálculo de minutos exacto es un
    problema aparte que se aborda después.
    """
    names = set()
    for p in side.get("starters", []):
        names.add(normalize_name(p["name"]))
    for p in side.get("bench", []):
        names.add(normalize_name(p["name"]))
    for sub in side.get("substitutions", []):
        if sub.get("out"):
            names.add(normalize_name(sub["out"]["name"]))
        if sub.get("in"):
            names.add(normalize_name(sub["in"]["name"]))
    return names


def player_minutes(side: dict, match_length=MATCH_LENGTH):
    """
    Devuelve {nombre: (dorsal, minuto_inicio, minuto_fin)} para todos los
    jugadores que llegaron a pisar el campo en ese partido, a partir de
    starters/bench/substitutions de un lado (home o away) del JSON del partido.
    """
    intervals = {}

    starters_by_name = {normalize_name(p["name"]): p["dorsal"] for p in side.get("starters", [])}
    for name, dorsal in starters_by_name.items():
        intervals[name] = [dorsal, 0, match_length]  # por defecto, todo el partido

    # aplica las sustituciones en orden de minuto
    subs = sorted(side.get("substitutions", []), key=lambda s: s["minute"])
    for sub in subs:
        minute = sub["minute"]
        out_p, in_p = sub.get("out"), sub.get("in")
        out_name = normalize_name(out_p["name"]) if out_p else None
        in_name = normalize_name(in_p["name"]) if in_p else None
        if out_p and out_name in intervals:
            intervals[out_name][2] = minute
        elif out_p:
            # jugador que sale pero no estaba registrado como titular (raro) -> lo ignoramos
            pass
        if in_p:
            if in_name in intervals:
                # reentra tras haber salido antes (raro, pero por si acaso)
                intervals[in_name][2] = match_length
            else:
                intervals[in_name] = [in_p["dorsal"], minute, match_length]

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
    player_call_ups = defaultdict(int)
    player_titular = defaultdict(int)
    player_minutes_total = defaultdict(int)
    player_goals_total = defaultdict(int)
    player_goals_conceded_total = defaultdict(int)
    player_dorsal = {}
    player_team = {}
    player_ranges = defaultdict(list)  # nombre -> lista de (start, end) por partido

    goals_total_seen = 0
    goals_skipped = 0
    subs_total_seen = 0
    matches_with_zero_subs = 0

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

        # Convocatorias: cualquiera que aparezca en Titulars o Suplents de
        # ese partido cuenta como convocado, haya llegado a jugar o no. Esto
        # es independiente del cálculo de minutos (que depende de que las
        # sustituciones estén bien leídas) — aquí solo miramos si el nombre
        # aparece listado en la ficha del equipo para ese partido.
        # "Titular" y "Suplente" son categorías que se excluyen entre sí y
        # suman el total de convocatorias: titular = empezó el partido en el
        # once inicial; suplente = empezó en el banquillo, haya llegado a
        # jugar o no.
        for side_name, side in ((home_name, home), (away_name, away)):
            for p in side.get("starters", []):
                name = normalize_name(p["name"])
                player_call_ups[name] += 1
                player_titular[name] += 1
                player_dorsal.setdefault(name, p["dorsal"])
                player_team.setdefault(name, side_name)
            for p in side.get("bench", []):
                name = normalize_name(p["name"])
                player_call_ups[name] += 1
                player_dorsal.setdefault(name, p["dorsal"])
                player_team.setdefault(name, side_name)

        # goles: hay que decidir de qué equipo es cada gol comparando el
        # autor con las plantillas de cada lado. Usamos roster_names (titulares
        # + suplentes + sustituciones) en vez de las intervals de minutos, para
        # que esto funcione ya mismo aunque el cálculo de minutos por
        # sustitución todavía no esté perfeccionado (eso se aborda aparte).
        # Si es "own_goal", el gol cuenta A FAVOR del equipo contrario y EN
        # CONTRA del equipo del autor.
        home_names = roster_names(home)
        away_names = roster_names(away)

        for goal in match.get("goals", []):
            scorer = normalize_name(goal["scorer"])
            minute = goal["minute"]
            b = bucket_index(minute)
            is_own_goal = goal.get("type") == "own_goal"
            goals_total_seen += 1

            if scorer in home_names:
                scoring_team, conceding_team = (away_name, home_name) if is_own_goal else (home_name, away_name)
            elif scorer in away_names:
                scoring_team, conceding_team = (home_name, away_name) if is_own_goal else (away_name, home_name)
            else:
                # autor no encontrado en ninguna plantilla (nombre distinto entre
                # tabla de goles y alineación); se ignora para las stats de equipo
                goals_skipped += 1
                print(f"  AVISO: gol de '{scorer}' (min {minute}) en {home_name} vs {away_name} "
                      f"no coincide con ningún jugador de la alineación de ese partido — se descarta.")
                if goals_skipped <= 20:
                    print(f"    DIAGNOSTICO — jugadores detectados en {home_name} ({len(home_names)}): "
                          f"{sorted(home_names)}")
                    print(f"    DIAGNOSTICO — jugadores detectados en {away_name} ({len(away_names)}): "
                          f"{sorted(away_names)}")
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
    all_player_names = set(player_matches.keys()) | set(player_call_ups.keys())
    for name in all_player_names:
        matches = player_matches.get(name, 0)
        call_ups = player_call_ups.get(name, 0)
        titular = player_titular.get(name, 0)
        suplente = call_ups - titular
        minutes_total = player_minutes_total[name]
        position = positions.get(name, "Sin definir")
        entry = {
            "name": name,
            "dorsal": player_dorsal.get(name),
            "team": player_team.get(name),
            "position": position,
            "callUpsTotal": call_ups,
            "titularTotal": titular,
            "suplenteTotal": suplente,
            "matches": matches,
            "minutesTotal": minutes_total,
            "minutesAvg": round(minutes_total / matches, 1) if matches else 0,
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

    missing = [n for n in players_out if players_out[n]["position"] == "Sin definir"]
    if missing:
        print(f"\nAviso: {len(missing)} jugadores sin posición asignada en positions.json.")
        print("(la web los mostrará igualmente, solo que sin ese dato)")


if __name__ == "__main__":
    main()
