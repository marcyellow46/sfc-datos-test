"""
check_altas_bajas.py
=====================
Cada día (normalmente se lanza a las 21:00 hora de España) descarga la ficha
de cada equipo del grupo y compara su listado de "Jugadors/es" con el
guardado el día anterior, para detectar:
  - ALTA: un jugador que aparece nuevo en la lista
  - BAJA: un jugador que ha desaparecido de la lista

Identifica a cada jugador por su ID único de la FCF (igual que el resto del
proyecto), con el nombre como respaldo si por lo que sea faltara el ID.

Genera/actualiza:
  - data/rosters/<equipo>.json   -> foto de la plantilla actual de cada
                                     equipo (para poder comparar mañana)
  - site/data/altas_bajas.json   -> historial completo de altas/bajas de
                                     todos los equipos, para que lo lea la web

USO:
    python check_altas_bajas.py
"""

import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scraper

DATA_DIR = Path(__file__).parent / "data"
ROSTERS_DIR = DATA_DIR / "rosters"
ROSTERS_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA_DIR = Path(__file__).parent / "site" / "data"
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_PATH = SITE_DATA_DIR / "altas_bajas.json"

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def formatted_now_madrid() -> str:
    """Ej: '26 de Julio a las 18:50' (hora de Madrid, con o sin horario de verano)."""
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    mes = MESES_ES[now.month - 1].capitalize()
    return f"{now.day} de {mes} a las {now.strftime('%H:%M')}"


def safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()


def player_key(p: dict) -> str:
    return p["player_id"] if p.get("player_id") else f"noid:{p['name']}"


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {}


def main():
    today = date.today().isoformat()
    team_urls = scraper.discover_team_equip_urls()
    print(f"Equipos encontrados: {len(team_urls)}")

    history = load_history()
    total_altas = 0
    total_bajas = 0

    for team_name, equip_url in team_urls.items():
        print(f"Comprobando plantilla: {team_name}")
        try:
            current_players = scraper.fetch_team_roster(equip_url)
        except Exception as e:
            print(f"  ERROR al descargar {equip_url}: {e}")
            continue

        current_by_key = {player_key(p): p["name"] for p in current_players}

        snapshot_path = ROSTERS_DIR / f"{safe_filename(team_name)}.json"
        previous_by_key = {}
        if snapshot_path.exists():
            previous_by_key = json.loads(snapshot_path.read_text(encoding="utf-8"))

        altas = [name for key, name in current_by_key.items() if key not in previous_by_key]
        bajas = [name for key, name in previous_by_key.items() if key not in current_by_key]

        if altas or bajas:
            events = history.setdefault(team_name, [])
            for name in altas:
                events.append({"jugador": name, "tipo": "alta", "fecha": today})
                print(f"  ALTA: {name}")
            for name in bajas:
                events.append({"jugador": name, "tipo": "baja", "fecha": today})
                print(f"  BAJA: {name}")
            total_altas += len(altas)
            total_bajas += len(bajas)

        snapshot_path.write_text(
            json.dumps(current_by_key, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    history["_meta"] = {"lastUpdated": formatted_now_madrid()}
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo. {total_altas} altas y {total_bajas} bajas detectadas hoy.")


if __name__ == "__main__":
    main()
