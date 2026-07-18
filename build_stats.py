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
CORRECTIONS_PATH = Path(__file__).parent / "corrections.json"
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
DEBUG_PLAYER_NAME_FILTER = ""  # ejemplo: "FELEZ NAVARRO"


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


def _sign(x):
    return (x > 0) - (x < 0)


def _new_key_moments():
    return {
        "early1_10For": 0, "early1_10Against": 0,
        "halfEnd40_45For": 0, "halfEnd40_45Against": 0,
        "halfStart45_50For": 0, "halfStart45_50Against": 0,
        "lateDecisiveFor": 0, "lateDecisiveAgainst": 0,
        "quickResponseAfterScoringFor": 0, "quickResponseAfterScoringAgainst": 0,
        "quickResponseAfterConcedingFor": 0, "quickResponseAfterConcedingAgainst": 0,
    }


def load_positions():
    if not POSITIONS_PATH.exists():
        return {}
    raw = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    return {normalize_name(k): v for k, v in raw.items()}


def load_corrections():
    if not CORRECTIONS_PATH.exists():
        return []
    return json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))


def apply_corrections(match: dict, match_filename: str, corrections: list) -> dict:
    """
    Aplica correcciones manuales a un partido concreto, ANTES de agregar sus
    datos. Se usa para arreglar errores puntuales de la propia acta de la
    FCF (p.ej. una sustitución registrada con el jugador equivocado) sin
    tocar el archivo original descargado — así la corrección sobrevive
    aunque se vuelva a descargar la temporada entera más adelante.

    Formato de cada corrección en corrections.json:
    {
      "match_file": "nombre-exacto-del-archivo.json",
      "reason": "texto libre explicando el porqué (solo para referencia)",
      "reassign_player": {
        "from_id": "ID que aparece por error en la acta",
        "to_id": "ID del jugador real",
        "to_name": "NOMBRE, DEL JUGADOR REAL",
        "to_dorsal": 20
      }
    }
    """
    relevant = [c for c in corrections if c.get("match_file") == match_filename]
    if not relevant:
        return match

    for c in relevant:
        r = c.get("reassign_player")
        if not r:
            continue
        from_id, to_id = r["from_id"], r["to_id"]
        to_name, to_dorsal = r.get("to_name"), r.get("to_dorsal")

        def fix(p):
            if p and p.get("player_id") == from_id:
                p["player_id"] = to_id
                if to_name:
                    p["name"] = to_name
                if to_dorsal is not None:
                    p["dorsal"] = to_dorsal

        for side in (match["home"], match["away"]):
            for p in side.get("starters", []) + side.get("bench", []):
                fix(p)
            for sub in side.get("substitutions", []):
                fix(sub.get("out"))
                fix(sub.get("in"))
        for g in match.get("goals", []):
            if g.get("scorer_id") == from_id:
                g["scorer_id"] = to_id
                if to_name:
                    g["scorer"] = to_name

        print(f"  [correccion aplicada] {match_filename}: {c.get('reason', '(sin motivo indicado)')} "
              f"(id {from_id} -> {to_id})")

    return match


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


def compute_yellow_cycle(team_schedule: list, card_jornadas: set):
    """
    Simula la acumulación de amarillas y su reseteo por sanción, jornada a
    jornada, siguiendo el calendario real del EQUIPO (no solo los partidos
    en los que jugó el propio jugador, porque la sanción se cumple con el
    calendario del equipo).

    Regla: al llegar a 5 amarillas (o 10, 15...), el contador se queda
    "a la espera" — se sigue mostrando esa 5ª amarilla en naranja hasta que
    el equipo dispute su SIGUIENTE partido (se entiende que ahí cumple el
    partido de sanción); en cuanto ese partido pasa, el contador se pone a
    0 y se suma un ciclo completado.

    Devuelve (ciclos_completados, amarillas_actuales_del_ciclo).
    """
    tally = 0
    cycles = 0
    awaiting_reset = False
    for j in sorted(team_schedule):
        if awaiting_reset:
            tally = 0
            cycles += 1
            awaiting_reset = False
        if j in card_jornadas:
            tally += 1
            if tally == 5:
                awaiting_reset = True
    return cycles, tally


def main():
    positions = load_positions()
    corrections = load_corrections()
    match_files = sorted(MATCHES_DIR.glob("*.json"))
    if not match_files:
        print("No hay partidos en data/matches/. Ejecuta antes scraper.py")
        return

    # acumuladores
    team_played = defaultdict(int)
    team_goals_against_total = defaultdict(int)
    team_gf_buckets = defaultdict(lambda: [0] * 6)
    team_ga_buckets = defaultdict(lambda: [0] * 6)
    team_key_moments = defaultdict(_new_key_moments)

    player_matches = defaultdict(int)
    player_call_ups = defaultdict(int)
    player_titular = defaultdict(int)
    player_minutes_total = defaultdict(int)
    player_goals_total = defaultdict(int)
    player_goals_conceded_total = defaultdict(int)
    player_dorsal = {}
    player_team = {}
    player_name = {}  # clave -> nombre normalizado, para mostrar en la web

    team_jornadas = defaultdict(set)          # equipo -> {jornadas que ha disputado}
    player_yellow_jornadas = defaultdict(set)  # clave jugador -> {jornadas en las que vio amarilla}

    goals_total_seen = 0
    goals_skipped = 0
    subs_total_seen = 0
    matches_with_zero_subs = 0

    debug_filter = DEBUG_PLAYER_NAME_FILTER.strip().upper()

    for f in match_files:
        match = json.loads(f.read_text(encoding="utf-8"))
        match = apply_corrections(match, f.name, corrections)
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

        jornada = match.get("jornada")
        if jornada is not None:
            team_jornadas[home_name].add(jornada)
            team_jornadas[away_name].add(jornada)

        for side_name, side in ((home_name, home), (away_name, away)):
            for c in side.get("cards", []):
                if c.get("type") != "yellow":
                    continue
                key = player_key(c.get("player_id"), c["name"])
                name = normalize_name(c["name"])
                player_name.setdefault(key, name)
                if jornada is not None:
                    player_yellow_jornadas[key].add(jornada)

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
        # Primera pasada: solo determinar de qué equipo es cada gol y
        # dejarlos ordenados por minuto (hace falta el orden real para
        # calcular el marcador en vivo y los "momentos clave" después).
        home_keys = roster_keys(home)
        away_keys = roster_keys(away)

        valid_goals = []
        for goal in match.get("goals", []):
            scorer_name = normalize_name(goal["scorer"])
            scorer_key = player_key(goal.get("scorer_id"), goal["scorer"])
            minute = goal["minute"]
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

            valid_goals.append({
                "minute": minute,
                "scoring_team": scoring_team,
                "conceding_team": conceding_team,
                "is_own_goal": is_own_goal,
                "scorer_key": scorer_key,
                "scorer_name": scorer_name,
            })

        valid_goals.sort(key=lambda g: g["minute"])

        # Segunda pasada: con los goles ya ordenados, aplicamos los tramos de
        # siempre y calculamos los "momentos clave" llevando el marcador en vivo.
        home_score, away_score = 0, 0
        prev_goal = None  # {"minute":, "scoring_team":, "conceding_team":} del gol anterior del partido
        for g in valid_goals:
            minute = g["minute"]
            scoring_team, conceding_team = g["scoring_team"], g["conceding_team"]
            b = bucket_index(minute)

            team_gf_buckets[scoring_team][b] += 1
            team_ga_buckets[conceding_team][b] += 1
            team_goals_against_total[conceding_team] += 1

            if not g["is_own_goal"]:
                player_goals_total[g["scorer_key"]] += 1
                player_name.setdefault(g["scorer_key"], g["scorer_name"])

            # goles encajados por el portero que estuviera en el campo en ese minuto
            conceding_side_intervals = home_intervals if conceding_team == home_name else away_intervals
            for key, (dorsal, name, start, end) in conceding_side_intervals.items():
                if positions.get(name) == "Portero" and start <= minute <= end:
                    player_goals_conceded_total[key] += 1

            # -------- momentos clave --------
            km_scoring = team_key_moments[scoring_team]
            km_conceding = team_key_moments[conceding_team]

            if 1 <= minute <= 10:
                km_scoring["early1_10For"] += 1
                km_conceding["early1_10Against"] += 1
            if 40 <= minute <= 45:
                km_scoring["halfEnd40_45For"] += 1
                km_conceding["halfEnd40_45Against"] += 1
            if 45 <= minute <= 50:
                km_scoring["halfStart45_50For"] += 1
                km_conceding["halfStart45_50Against"] += 1

            # gol decisivo tardío: compara el signo del marcador (a favor del
            # local) antes y después de este gol concreto.
            diff_before = home_score - away_score
            if scoring_team == home_name:
                home_score += 1
            else:
                away_score += 1
            diff_after = home_score - away_score

            if minute >= 80 and _sign(diff_before) != _sign(diff_after):
                km_scoring["lateDecisiveFor"] += 1
                km_conceding["lateDecisiveAgainst"] += 1

            # Respuesta rápida: este gol cae dentro de los 5 minutos
            # siguientes al gol anterior del partido. Se distingue según qué
            # fue ese gol anterior PARA CADA equipo implicado en el gol
            # actual: si el equipo que marca/encaja ahora había marcado o
            # encajado el gol anterior.
            if prev_goal is not None and (minute - prev_goal["minute"]) <= 5:
                prev_scoring, prev_conceding = prev_goal["scoring_team"], prev_goal["conceding_team"]

                # el equipo que ahora MARCA (scoring_team):
                if prev_scoring == scoring_team:
                    km_scoring["quickResponseAfterScoringFor"] += 1      # marcó, y vuelve a marcar rápido
                elif prev_conceding == scoring_team:
                    km_scoring["quickResponseAfterConcedingFor"] += 1    # había encajado, responde rápido

                # el equipo que ahora ENCAJA (conceding_team):
                if prev_scoring == conceding_team:
                    km_conceding["quickResponseAfterScoringAgainst"] += 1    # había marcado, encaja justo después
                elif prev_conceding == conceding_team:
                    km_conceding["quickResponseAfterConcedingAgainst"] += 1  # ya encajaba, encaja otra vez rápido

            prev_goal = {"minute": minute, "scoring_team": scoring_team, "conceding_team": conceding_team}

    # -------- construir teams.json --------
    teams_out = {}
    for team, played in team_played.items():
        goals_for_total = sum(team_gf_buckets[team])
        teams_out[team] = {
            "name": team,
            "matchesPlayed": played,
            "goalsForTotal": goals_for_total,
            "goalsForAvg": round(goals_for_total / played, 2),
            "goalsAgainstTotal": team_goals_against_total[team],
            "goalsAgainstAvg": round(team_goals_against_total[team] / played, 2),
            "gfBucketsTotal": team_gf_buckets[team],
            "gfBucketsAvg": [round(v / played, 2) for v in team_gf_buckets[team]],
            "gaBucketsTotal": team_ga_buckets[team],
            "gaBucketsAvg": [round(v / played, 2) for v in team_ga_buckets[team]],
            "keyMoments": team_key_moments[team],
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
        team = player_team.get(key)
        schedule = team_jornadas.get(team, set())
        card_jornadas = player_yellow_jornadas.get(key, set())
        yellow_cycles, yellow_tally = compute_yellow_cycle(schedule, card_jornadas)

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
            "yellowCardsTotal": len(card_jornadas),
            "yellowCardsCycles": yellow_cycles,
            "yellowCardsTally": yellow_tally,
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
