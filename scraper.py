"""
scraper.py
==========
Descarga y parsea las actas de la FCF (fcf.cat) para una competición/grupo/temporada
concretos, y deja un JSON por partido en data/matches/.

USO:
    python scraper.py

CONFIGURACIÓN: ver el bloque CONFIG más abajo.

CÓMO FUNCIONA (2 pasos):
  1. Recorre las páginas de resultados por jornada
     (https://www.fcf.cat/resultats/<season>/<sport>/<competition>/<group>/jornada-N)
     y saca de ahí, para cada partido: equipos, marcador, y la URL de la acta.
     Esto es más fiable que intentar reconstruir la URL de la acta a mano, porque
     cada equipo lleva un "código de categoría" en la URL (1cat, elit, aa...) que
     no es predecible.
  2. Para cada acta encontrada, descarga la página y extrae:
     titulares, suplentes, equipo técnico, sustituciones (con minuto),
     goles (con minuto y autor), tarjetas (con minuto), árbitros y estadio.

NOTA IMPORTANTE:
  No he podido inspeccionar el HTML "crudo" de fcf.cat (solo una versión ya
  convertida a texto/markdown), así que el parseo se apoya en los textos de
  cabecera reales que sí he confirmado ("Titulars", "Suplents", "Substitucions",
  "Targetes", "Gols", "Àrbitres", "Estadi"...) en vez de en clases CSS, para que
  sea más resistente a cambios de maquetación. Aun así, es MUY probable que la
  primera vez que lo ejecutes contra la web real haga falta ajustar algún
  detalle — el código está comentado para que sea fácil de depurar por
  bloques (activa DEBUG=True y revisa data/matches/_debug_*.html).
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ----------------------------- CONFIG ---------------------------------------

SEASON = "2526"                       # temporada 2025-2026
SPORT = "futbol-11"
COMPETITION = "lliga-elit"
GROUP = "grup-1"
MAX_JORNADAS = 34                     # límite de seguridad; se detiene antes si no hay más
REQUEST_DELAY_SECONDS = 1.0           # ser educado con el servidor de la FCF
DEBUG = False                         # True -> guarda el html de cada página descargada
FORCE_REFRESH = False                  # True -> re-parsea TODO aunque el JSON ya exista.
                                       # Ponlo en True puntualmente cuando cambies la
                                       # lógica de parseo (como ahora, para corregir los
                                       # partidos guardados con el nombre de equipo local
                                       # vacío). Para el uso normal semanal, déjalo en
                                       # False: así solo se descargan los partidos nuevos
                                       # y no se vuelve a golpear el servidor de la FCF
                                       # pidiendo los ~240 partidos ya guardados.

BASE = "https://www.fcf.cat"
CALENDAR_URL = f"{BASE}/calendari/{SEASON}/{SPORT}/{COMPETITION}/{GROUP}"
RESULTS_URL_TMPL = f"{BASE}/resultats/{SEASON}/{SPORT}/{COMPETITION}/{GROUP}/jornada-{{n}}"  # fallback, ver más abajo

DATA_DIR = Path(__file__).parent / "data"
MATCHES_DIR = DATA_DIR / "matches"
MATCHES_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SFCDatosBot/1.0; +https://www.sfcdatos.com)"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_soup(url: str) -> BeautifulSoup:
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    if DEBUG:
        fname = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-120:] + ".html"
        (DATA_DIR / "_debug").mkdir(exist_ok=True)
        (DATA_DIR / "_debug" / fname).write_text(resp.text, encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return BeautifulSoup(resp.text, "html.parser")


# ------------------------- PASO 1: DESCUBRIR PARTIDOS ------------------------

def discover_matches():
    """
    Descarga la página /calendari/ del grupo (UNA sola petición) y extrae
    todos los partidos de la temporada completa: cada partido ya trae ahí
    mismo el enlace a su acta, el marcador y los dos equipos. Esto es más
    eficiente que recorrer jornada-1..jornada-N (que era el método anterior,
    dejado como discover_matches_by_jornada() más abajo por si esta página
    cambiase de estructura).

    Devuelve una lista de dicts:
    {"jornada": n, "home": "...", "away": "...", "score": "1-1", "acta_url": "https://..."}
    """
    soup = get_soup(CALENDAR_URL)
    matches = []
    current_jornada = None

    for tr in soup.find_all("tr"):
        # Cabecera de cada bloque: una fila del tipo "Jornada 14 | ... | 11-01-2026 | ..."
        first_cell = tr.find(["td", "th"])
        if first_cell:
            m = re.match(r"\s*Jornada\s+(\d+)", first_cell.get_text())
            if m:
                current_jornada = int(m.group(1))
                continue

        acta_link = tr.find("a", href=re.compile(r"/acta/"))
        if not acta_link:
            continue

        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        # Cada fila tiene 4 enlaces con href "/equip/": nombre local, escudo
        # local, escudo visitante, nombre visitante. Los de escudo envuelven
        # solo una <img> y no llevan texto, así que los descartamos y nos
        # quedamos solo con los dos que sí tienen nombre.
        team_links_all = tr.find_all("a", href=re.compile(r"/equip/"))
        team_links = [a for a in team_links_all if a.get_text(strip=True)]
        home = team_links[0].get_text(strip=True) if len(team_links) > 0 else None
        away = team_links[1].get_text(strip=True) if len(team_links) > 1 else None

        # El marcador son las dos celdas puramente numéricas de la fila
        # (una a cada lado del enlace a la acta).
        nums = [c.get_text(strip=True) for c in cells if c.get_text(strip=True).isdigit()]
        score = f"{nums[0]}-{nums[1]}" if len(nums) >= 2 else None

        acta_url = acta_link["href"]
        if not acta_url.startswith("http"):
            acta_url = BASE + acta_url

        matches.append({
            "jornada": current_jornada,
            "home": home,
            "away": away,
            "score": score,
            "acta_url": acta_url,
        })

    print(f"Total partidos encontrados en el calendario: {len(matches)}")
    return matches


def discover_matches_by_jornada():
    """
    MÉTODO ALTERNATIVO (fallback): recorre jornada-1..jornada-N por si algún
    día /calendari/ deja de existir o cambia de formato. Más lento (una
    petición por jornada) pero funciona sobre /resultats/.../jornada-N.
    """
    matches = []
    for n in range(1, MAX_JORNADAS + 1):
        url = RESULTS_URL_TMPL.format(n=n)
        try:
            soup = get_soup(url)
        except requests.HTTPError:
            print(f"Jornada {n}: no disponible, paro aquí.")
            break

        acta_links = soup.find_all("a", href=re.compile(r"/acta/"))
        if not acta_links:
            print(f"Jornada {n}: sin partidos encontrados, paro aquí.")
            break

        seen_urls = set()
        for link in acta_links:
            acta_url = link["href"]
            if not acta_url.startswith("http"):
                acta_url = BASE + acta_url
            if acta_url in seen_urls:
                continue
            seen_urls.add(acta_url)

            score_match = re.search(r"(\d+)\s*-\s*(\d+)", link.get_text())
            score = f"{score_match.group(1)}-{score_match.group(2)}" if score_match else None

            container = link.find_parent(["li", "div", "tr"]) or link.parent
            team_links = container.find_all("a", href=re.compile(r"/equip/")) if container else []
            home = team_links[0].get_text(strip=True) if len(team_links) > 0 else None
            away = team_links[1].get_text(strip=True) if len(team_links) > 1 else None

            matches.append({
                "jornada": n, "home": home, "away": away,
                "score": score, "acta_url": acta_url,
            })
        print(f"Jornada {n}: {len(seen_urls)} partidos.")
    return matches


# ------------------------------ PASO 2: PARSEAR ACTA -------------------------

def _find_section_table(soup: BeautifulSoup, header_text: str):
    """
    Busca un texto de cabecera exacto (p.ej. 'Titulars') y devuelve la
    primera <table> que aparece después de él en el documento.
    """
    header = soup.find(string=re.compile(rf"^\s*{re.escape(header_text)}\s*$"))
    if not header:
        return None
    node = header.find_parent()
    table = node.find_next("table") if node else None
    return table


def _parse_lineup_table(table):
    """Devuelve lista de {"dorsal": int, "name": str, "player_url": str|None}."""
    players = []
    if not table:
        return players
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        dorsal_txt = cells[0].get_text(strip=True)
        if not dorsal_txt.isdigit():
            continue
        link = cells[1].find("a")
        name = link.get_text(strip=True) if link else cells[1].get_text(strip=True)
        player_url = link["href"] if link else None
        players.append({"dorsal": int(dorsal_txt), "name": name, "player_url": player_url})
    return players


def _parse_substitutions_global(soup, debug_label=None):
    """
    Igual que con los goles: en vez de depender de encontrar primero la
    tabla que sigue (o que envuelve) al texto "Substitucions" —que resultó
    no encontrarse NUNCA en los 240 partidos reales, el mismo tipo de
    fragilidad que ya vimos con "Gols"—, recorremos TODAS las filas <tr>
    del documento.

    Confirmado con una acta real: cada sustitución son dos filas seguidas,
    "sale" (minuto + dorsal + jugador) e "entra" justo debajo. La fila
    "entra" puede tener 2 celdas (dorsal + jugador, sin celda de minuto) o
    3 (celda de minuto vacía + dorsal + jugador) según cómo la renderice
    la web en cada caso — antes solo contemplaba la variante de 3 celdas,
    por eso no encontraba ninguna "entra". Ahora acepto las dos.
    """
    all_rows = soup.find_all("tr")

    def row_as_out(cells):
        # fila "sale": minuto + dorsal + enlace a jugador (3+ celdas)
        if len(cells) < 3:
            return None
        minute_txt = cells[0].get_text(strip=True).replace("'", "")
        dorsal_txt = cells[1].get_text(strip=True)
        link = cells[2].find("a", href=re.compile(r"/jugador/"))
        if not (minute_txt.isdigit() and dorsal_txt.isdigit() and link):
            return None
        return {"minute": int(minute_txt), "dorsal": int(dorsal_txt), "name": link.get_text(strip=True)}

    def row_as_in(cells):
        # fila "entra": no lleva celda de minuto (esa celda usa rowspan desde
        # la fila "sale" de arriba, así que aquí ni siquiera existe un hueco
        # vacío). La forma real es [dorsal][jugador] seguido de lo que sea
        # (p.ej. el icono de la flecha azul de "entra"), así que solo miramos
        # las DOS primeras celdas y ya, sin importar cuántas vengan detrás.
        if len(cells) >= 2:
            dorsal_txt = cells[0].get_text(strip=True)
            link = cells[1].find("a", href=re.compile(r"/jugador/"))
            if dorsal_txt.isdigit() and link:
                return {"dorsal": int(dorsal_txt), "name": link.get_text(strip=True)}
        # variante alternativa, por si alguna acta sí lleva un hueco vacío
        # de la celda de minuto en vez de omitirla del todo
        if len(cells) >= 3 and cells[0].get_text(strip=True) == "":
            dorsal_txt = cells[1].get_text(strip=True)
            link = cells[2].find("a", href=re.compile(r"/jugador/"))
            if dorsal_txt.isdigit() and link:
                return {"dorsal": int(dorsal_txt), "name": link.get_text(strip=True)}
        return None

    events = []
    unpaired_sale = 0
    raw_dump_left = 2  # cuántas veces mostramos el HTML crudo de la fila que falla
    i = 0
    while i < len(all_rows):
        out_player = row_as_out(all_rows[i].find_all("td"))
        if out_player and i + 1 < len(all_rows):
            in_player = row_as_in(all_rows[i + 1].find_all("td"))
            if in_player:
                events.append({
                    "minute": out_player["minute"],
                    "out": {"dorsal": out_player["dorsal"], "name": out_player["name"]},
                    "in": in_player,
                })
                i += 2
                continue
            unpaired_sale += 1
            if debug_label and raw_dump_left > 0:
                raw_dump_left -= 1
                print(f"    [debug-html] {debug_label}: fila 'sale' encontrada "
                      f"({out_player}), pero la fila siguiente no encaja como 'entra'. "
                      f"HTML crudo de la fila siguiente:\n"
                      f"    {all_rows[i + 1] if i + 1 < len(all_rows) else '(no hay fila siguiente)'}")
        i += 1

    if debug_label:
        print(f"    [debug] {debug_label}: {len(events)} sustituciones emparejadas "
              f"({unpaired_sale} filas 'sale' sin pareja 'entra' detectada).")

    return events


def _parse_goals(soup):
    """
    En vez de buscar primero la tabla que sigue al texto "Gols" (frágil: si
    "Gols" es la propia cabecera de esa tabla en lugar de un título aparte,
    "la siguiente tabla" es la equivocada — esto es justo lo que estaba
    pasando: 0 goles detectados en los 240 partidos reales), recorremos
    TODAS las filas <tr> del documento y nos quedamos con las que tienen
    forma de fila de gol:
      - primera celda con un marcador tipo "1 - 0"
      - un enlace a un jugador (href "/jugador/") en la fila
      - última celda con un minuto tipo "45'"
    Esto es más robusto porque no depende de dónde esté colocada la tabla
    ni de cómo se llame su cabecera.
    """
    goals = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        score_txt = cells[0].get_text(strip=True)
        if not re.match(r"^\d+\s*-\s*\d+$", score_txt):
            continue

        link = row.find("a", href=re.compile(r"/jugador/"))
        if not link:
            continue
        scorer = link.get_text(strip=True)

        minute_txt = cells[-1].get_text(strip=True).replace("'", "")
        if not minute_txt.isdigit():
            continue

        # Intento de detectar el tipo de gol por el icono (alt/src de la img).
        # AJUSTAR aquí si se confirma un patrón distinto: de momento clasifica
        # por palabras clave típicas ("penal", "propia") si aparecen en
        # alt/title/src de alguna imagen de la fila.
        goal_type = "normal"
        img = row.find("img")
        if img:
            hint = " ".join(filter(None, [img.get("alt", ""), img.get("title", ""), img.get("src", "")])).lower()
            if "propia" in hint:
                goal_type = "own_goal"
            elif "penal" in hint:
                goal_type = "penalty"

        goals.append({
            "score_after": score_txt,
            "scorer": scorer,
            "minute": int(minute_txt),
            "type": goal_type,
        })
    return goals


def _parse_cards(table):
    cards = []
    if not table:
        return cards
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        dorsal_txt = cells[0].get_text(strip=True)
        link = cells[1].find("a")
        name = link.get_text(strip=True) if link else cells[1].get_text(strip=True)
        minute_txt = cells[2].get_text(strip=True).replace("'", "")
        if not (dorsal_txt.isdigit() and minute_txt.isdigit()):
            continue
        cards.append({"dorsal": int(dorsal_txt), "name": name, "minute": int(minute_txt)})
    return cards


_debug_subs_calls = 0
_debug_subs_limit = 3


def parse_acta(acta_url: str) -> dict:
    global _debug_subs_calls
    soup = get_soup(acta_url)

    # Nombres de equipo y marcador desde el título de la página / cabecera.
    title = soup.find("title")
    title_txt = title.get_text() if title else ""

    # Misma situación que en discover_matches(): la cabecera de la acta
    # repite escudo+nombre para cada equipo (y todo el bloque aparece DOS
    # veces en la página), así que filtramos los enlaces sin texto (escudos)
    # y nos quedamos con los dos primeros nombres reales.
    team_headers_all = soup.find_all("a", href=re.compile(r"/equip/"))
    team_headers = [a for a in team_headers_all if a.get_text(strip=True)]
    home_name = team_headers[0].get_text(strip=True) if len(team_headers) > 0 else None
    away_name = team_headers[1].get_text(strip=True) if len(team_headers) > 1 else None

    score_match = re.search(r"(\d+)\s*-\s*(\d+)", soup.get_text())
    score = f"{score_match.group(1)}-{score_match.group(2)}" if score_match else None

    # Hay dos bloques "Titulars"/"Suplents"/"Targetes" (uno por equipo). Las
    # sustituciones ya no se localizan por cabecera (ver _parse_substitutions_global).
    titulars_tables = soup.find_all(string=re.compile(r"^\s*Titulars\s*$"))
    suplents_tables = soup.find_all(string=re.compile(r"^\s*Suplents\s*$"))
    cards_tables = soup.find_all(string=re.compile(r"^\s*Targetes\s*$"))

    def _resolve(text_node, parser_fn):
        """
        Prueba las dos formas posibles de localizar la tabla de una sección
        ("Titulars", "Suplents", "Substitucions", "Targetes") y se queda con
        la que produzca un resultado no vacío al parsearla:
          1. La tabla ANCESTRA del propio texto de cabecera (por si el texto
             es la cabecera de su propia tabla).
          2. La SIGUIENTE tabla del documento a partir de ese texto (por si
             el texto es un título aparte, antes de una tabla separada).
        No todas las secciones de la acta usan la misma estructura interna
        (así lo hemos comprobado: Titulars/Suplents usan una, Substitucions
        parece usar la otra), así que en vez de asumir una sola regla fija,
        probamos las dos y validamos por resultado.
        """
        own_table = text_node.find_parent("table")
        node = text_node.find_parent()
        next_table = node.find_next("table") if node else None

        for candidate in (own_table, next_table):
            if candidate is None:
                continue
            result = parser_fn(candidate)
            if result:
                return result
        return []

    home_starters = _resolve(titulars_tables[0], _parse_lineup_table) if len(titulars_tables) > 0 else []
    away_starters = _resolve(titulars_tables[1], _parse_lineup_table) if len(titulars_tables) > 1 else []
    home_subs_bench = _resolve(suplents_tables[0], _parse_lineup_table) if len(suplents_tables) > 0 else []
    away_subs_bench = _resolve(suplents_tables[1], _parse_lineup_table) if len(suplents_tables) > 1 else []
    home_cards = _resolve(cards_tables[0], _parse_cards) if len(cards_tables) > 0 else []
    away_cards = _resolve(cards_tables[1], _parse_cards) if len(cards_tables) > 1 else []

    # Sustituciones: escaneamos todo el documento (ver _parse_substitutions_global)
    # y repartimos cada evento a local o visitante según a qué plantilla
    # pertenece el jugador que sale (comparando contra titulares+suplentes,
    # ya localizados arriba).
    all_substitutions = _parse_substitutions_global(
        soup, debug_label=(acta_url if _debug_subs_calls < _debug_subs_limit else None)
    )
    _debug_subs_calls += 1
    home_roster = {p["name"] for p in home_starters} | {p["name"] for p in home_subs_bench}
    away_roster = {p["name"] for p in away_starters} | {p["name"] for p in away_subs_bench}
    home_substitutions = [e for e in all_substitutions if e["out"]["name"] in home_roster]
    away_substitutions = [e for e in all_substitutions if e["out"]["name"] in away_roster]

    goals = _parse_goals(soup)

    # fecha del partido (aparece como "Data: DD-MM-AAAA, HH:MMh")
    date_match = re.search(r"Data:\s*([\d\-]+),?\s*([\d:]+h)?", soup.get_text())
    date = date_match.group(1) if date_match else None

    return {
        "acta_url": acta_url,
        "date": date,
        "score": score,
        "home": {
            "name": home_name,
            "starters": home_starters,
            "bench": home_subs_bench,
            "substitutions": home_substitutions,
            "cards": home_cards,
        },
        "away": {
            "name": away_name,
            "starters": away_starters,
            "bench": away_subs_bench,
            "substitutions": away_substitutions,
            "cards": away_cards,
        },
        "goals": goals,   # goles del partido; se asignan a home/away comparando el autor con las plantillas
    }


# ------------------------------ MAIN -----------------------------------------

def main():
    print("Descubriendo partidos...")
    matches = discover_matches()
    print(f"Total partidos encontrados: {len(matches)}")

    index = []
    for m in matches:
        acta_id = re.sub(r"[^a-zA-Z0-9]+", "-", m["acta_url"].split("/acta/")[-1]).strip("-")
        out_path = MATCHES_DIR / f"{acta_id}.json"
        if out_path.exists() and not FORCE_REFRESH:
            index.append(m)
            continue  # ya descargado en una ejecución anterior
        try:
            print(f"Parseando: {m['home']} vs {m['away']} (J{m['jornada']})")
            data = parse_acta(m["acta_url"])
            data["jornada"] = m["jornada"]
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  ERROR parseando {m['acta_url']}: {e}")
        index.append(m)

    (DATA_DIR / "matches_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Listo.")


if __name__ == "__main__":
    main()
