"""
Construye a mano, a partir de las 3 actas reales que hemos leído en el chat
(J1, J19, J30 del Santfeliuenc), los JSON con el mismo formato que produce
scraper.py, para poder ejecutar build_stats.py con datos reales de verdad
y comprobar que el pipeline entero funciona.
"""
import json
from pathlib import Path

MATCHES_DIR = Path(__file__).parent / "data" / "matches"
MATCHES_DIR.mkdir(parents=True, exist_ok=True)


def starters(pairs):
    return [{"dorsal": d, "name": n, "player_url": None} for d, n in pairs]


def sub(minute, out_d, out_n, in_d, in_n):
    return {"minute": minute, "out": {"dorsal": out_d, "name": out_n}, "in": {"dorsal": in_d, "name": in_n}}


def goal(score_after, scorer, minute, gtype="normal"):
    return {"score_after": score_after, "scorer": scorer, "minute": minute, "type": gtype}


# ---------------------------------------------------------------- J1 ----
j1 = {
    "acta_url": "https://www.fcf.cat/acta/2526/futbol-11/lliga-elit/grup-1/elit/santfeliuenc-fc-a/elit/prat-ae-a",
    "date": "20-09-2025",
    "jornada": 1,
    "score": "1-2",
    "home": {
        "name": "SANTFELIUENC, F.C. A",
        "starters": starters([
            (13, "CASAMAYOR CONTEL, ANTONIO"), (3, "VILLEGAS SANTOS, ALBERT"),
            (4, "GARCÍA NACARINO, VÍCTOR"), (6, "VARESE NAFA, ANDRES"),
            (7, "MENDEZ GIRALDEZ, IVAN"), (10, "AVELLANEDA PLAZUELO, JOSE JOAQUIN"),
            (11, "BLASCO TORRENTE, PABLO"), (12, "CARESIA MESA, PAU"),
            (17, "AVILES DIAZ, ALEJANDRO"), (21, "GUILLEM ARMADA, SAUL"),
            (22, "CASARES ALGUACIL, MARC"),
        ]),
        "bench": [],
        "substitutions": [
            sub(58, 6, "VARESE NAFA, ANDRES", 18, "RODRIGUEZ JIMENEZ, CHRISTIAN"),
            sub(58, 21, "GUILLEM ARMADA, SAUL", 5, "SADURNI FABRELLAS, JOSEP"),
            sub(68, 7, "MENDEZ GIRALDEZ, IVAN", 20, "FELEZ NAVARRO, SERGI"),
            sub(68, 10, "AVELLANEDA PLAZUELO, JOSE JOAQUIN", 23, "OLAECHEA MARTÍNEZ, FRANCESC XAVIER"),
            sub(68, 17, "AVILES DIAZ, ALEJANDRO", 28, "COLLADO GUTIERREZ, JONATAN"),
            sub(84, 22, "CASARES ALGUACIL, MARC", 2, "MATEO QUEJIGO, ELOI"),
        ],
        "cards": [],
    },
    "away": {
        "name": "PRAT, A.E. A",
        "starters": starters([
            (13, "GUISERIS MIÑARRO, DANIEL"), (3, "PEÑA DOMINGO, ROGER"),
            (4, "GARCIA CABRERA, CARLOS"), (5, "ALDABÓ BENAQUE, POL"),
            (7, "PLUVINS RAMOS, XAVIER"), (9, "VIDAL GIRONES, RICARD"),
            (11, "PLAZA CREMADES, ALEX"), (20, "GOMEZ CASAS, RUBEN"),
            (21, "LAMELAS DOMINGUEZ, MARTIN"), (23, "CORTINA CABALLERO, ABEL"),
            (28, "VICTOR DELGADO, XAVI"),
        ]),
        "bench": [],
        "substitutions": [
            sub(22, 28, "VICTOR DELGADO, XAVI", 17, "CUEVAS LARDIES, NICOLAS DANIEL"),
            sub(46, 11, "PLAZA CREMADES, ALEX", 22, "PADILLA RUBIO, MARC"),
            sub(58, 7, "PLUVINS RAMOS, XAVIER", 8, "FONT MONTSERRAT, MARC"),
            sub(84, 21, "LAMELAS DOMINGUEZ, MARTIN", 18, "MUÑOZ VELA, MARC"),
        ],
        "cards": [],
    },
    "goals": [
        goal("0-1", "LAMELAS DOMINGUEZ, MARTIN", 6),
        goal("1-1", "BLASCO TORRENTE, PABLO", 11),
        goal("1-2", "LAMELAS DOMINGUEZ, MARTIN", 50),
    ],
}

# --------------------------------------------------------------- J19 ----
j19 = {
    "acta_url": "https://www.fcf.cat/acta/2526/futbol-11/lliga-elit/grup-1/elit/santfeliuenc-fc-a/elit/martinenc-fc-a",
    "date": "21-02-2026",
    "jornada": 19,
    "score": "1-3",
    "home": {
        "name": "SANTFELIUENC, F.C. A",
        "starters": starters([
            (13, "CASAMAYOR CONTEL, ANTONIO"), (2, "MATEO QUEJIGO, ELOI"),
            (3, "VILLEGAS SANTOS, ALBERT"), (7, "MENDEZ GIRALDEZ, IVAN"),
            (11, "BLASCO TORRENTE, PABLO"), (12, "CARESIA MESA, PAU"),
            (15, "HERVIAS MARTINEZ, MARIO"), (18, "RODRIGUEZ JIMENEZ, CHRISTIAN"),
            (19, "HONORATO TORREJON, KILIAN"), (21, "GUILLEM ARMADA, SAUL"),
            (22, "CASARES ALGUACIL, MARC"),
        ]),
        "bench": [],
        "substitutions": [
            sub(64, 15, "HERVIAS MARTINEZ, MARIO", 27, "FERNÁNDEZ FERNÁNDEZ, HÉCTOR"),
            sub(64, 19, "HONORATO TORREJON, KILIAN", 8, "CARBONELL GIL, MARC"),
            sub(78, 7, "MENDEZ GIRALDEZ, IVAN", 10, "AVELLANEDA PLAZUELO, JOSE JOAQUIN"),
            sub(78, 21, "GUILLEM ARMADA, SAUL", 23, "OLAECHEA MARTÍNEZ, FRANCESC XAVIER"),
            sub(89, 12, "CARESIA MESA, PAU", 9, "ALVAREZ CABO, SAUL"),
        ],
        "cards": [],
    },
    "away": {
        "name": "MARTINENC, F.C. A",
        "starters": starters([
            (1, "LAZARO ORTIZ, ALEJANDRO"), (5, "SARO SATRÚSTEGUI, ADRIÀ"),
            (6, "SOSA MORENO, JUAN"), (7, "FABIAN PASCUAL, VICTOR"),
            (8, "SUÁREZ POSTIGO, DANIEL"), (10, "TEJADA GALLARDO, EDGAR"),
            (11, "GONZALEZ VALTUEÑA, ANGEL"), (14, "GONZALEZ ALCANTARA, CARLOS"),
            (16, "ALARCON MILLAN, KEVIN"), (17, "ESPIGOL DE LEMUS, MAX"),
            (21, "NAVARRO LINARES, ADRIÁN"),
        ]),
        "bench": [],
        "substitutions": [
            sub(64, 21, "NAVARRO LINARES, ADRIÁN", 22, "BLASCO TORNE, GENIS"),
            sub(71, 16, "ALARCON MILLAN, KEVIN", 24, "SANCHEZ PONS, FERRAN"),
            sub(71, 11, "GONZALEZ VALTUEÑA, ANGEL", 9, "OSORIO BARROZO, FAVIO JULIAN"),
            sub(85, 7, "FABIAN PASCUAL, VICTOR", 15, "BANGUERO LASSO, YILSON EDUTH"),
            sub(89, 14, "GONZALEZ ALCANTARA, CARLOS", 25, "RIBERA"),
        ],
        "cards": [],
    },
    "goals": [
        goal("1-0", "RODRIGUEZ JIMENEZ, CHRISTIAN", 7),
        goal("1-1", "SUÁREZ POSTIGO, DANIEL", 36),
        goal("1-2", "SOSA MORENO, JUAN", 89),
        goal("1-3", "RIBERA", 89),
    ],
}

# --------------------------------------------------------------- J30 ----
j30 = {
    "acta_url": "https://www.fcf.cat/acta/2526/futbol-11/lliga-elit/grup-1/1cat/santfeliuenc-fc-a/elit/san-mauro-ud-a",
    "date": "16-05-2026",
    "jornada": 30,
    "score": "1-1",
    "home": {
        "name": "SANTFELIUENC, F.C. A",
        "starters": starters([
            (1, "VAZQUEZ ALONSO, MARC"), (3, "VILLEGAS SANTOS, ALBERT"),
            (6, "VARESE NAFA, ANDRES"), (7, "MENDEZ GIRALDEZ, IVAN"),
            (8, "CARBONELL GIL, MARC"), (12, "CARESIA MESA, PAU"),
            (17, "AVILES DIAZ, ALEJANDRO"), (19, "HONORATO TORREJON, KILIAN"),
            (21, "GUILLEM ARMADA, SAUL"), (22, "CASARES ALGUACIL, MARC"),
            (28, "DURAN MANZANILLA, HUGO"),
        ]),
        "bench": [],
        "substitutions": [
            sub(30, 28, "DURAN MANZANILLA, HUGO", 27, "FERNÁNDEZ FERNÁNDEZ, HÉCTOR"),
            sub(46, 8, "CARBONELL GIL, MARC", 15, "HERVIAS MARTINEZ, MARIO"),
            sub(46, 6, "VARESE NAFA, ANDRES", 2, "MATEO QUEJIGO, ELOI"),
            sub(46, 7, "MENDEZ GIRALDEZ, IVAN", 5, "SADURNI FABRELLAS, JOSEP"),
            sub(56, 3, "VILLEGAS SANTOS, ALBERT", 4, "GARCÍA NACARINO, VÍCTOR"),
            sub(63, 19, "HONORATO TORREJON, KILIAN", 10, "JIMENEZ IBARROLA, ERIC"),
            sub(63, 12, "CARESIA MESA, PAU", 9, "ALVAREZ CABO, SAUL"),
        ],
        "cards": [],
    },
    "away": {
        "name": "SAN MAURO, U.D. A",
        "starters": starters([
            (25, "MARTÍNEZ BENÍTEZ, CALEB"), (4, "MASEGOSA SOLÍS, ALBERT"),
            (5, "GARCÍA GARCÍA, JAVIER"), (6, "ENRIQUEZ DE LA ROSA, MARC"),
            (10, "ARIBAU CASALS, JORDI"), (11, "YÁÑEZ BORRÀS, PAU"),
            (12, "MERINAS CLOP, ERNEST"), (15, "ESPINOSA FIGUERAS, JAIRÓN RUBÉN"),
            (19, "CAÑERO CARMONA, ALEX"), (20, "GULIAS AGUILERA, MARC"),
            (21, "MARQUILLAS BONAVILA, GERARD"),
        ]),
        "bench": [],
        "substitutions": [
            sub(65, 12, "MERINAS CLOP, ERNEST", 17, "ROMEU MARQUES, POL"),
            sub(75, 6, "ENRIQUEZ DE LA ROSA, MARC", 18, "MORENO ORDOÑEZ, DAVID"),
            sub(84, 19, "CAÑERO CARMONA, ALEX", 16, "SARSANEDAS CONTRERAS, JOAO"),
        ],
        "cards": [],
    },
    "goals": [
        goal("1-0", "HONORATO TORREJON, KILIAN", 41),
        goal("1-1", "CAÑERO CARMONA, ALEX", 58),
    ],
}

for m in (j1, j19, j30):
    fname = m["acta_url"].split("/acta/")[-1].replace("/", "-") + ".json"
    (MATCHES_DIR / fname).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Guardado:", fname)
