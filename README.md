# SFC Datos — scraper + web

## Qué hay en esta carpeta

```
scraper.py             -> descubre partidos y parsea cada acta a JSON (data/matches/)
build_stats.py          -> agrega los partidos en data/teams.json y data/players.json
positions.json           -> tú rellenas aquí "Nombre del jugador" -> posición
build_real_sample.py     -> demo con 3 partidos reales ya cargados a mano (para probar sin depender del scraper)
requirements.txt
site/index.html          -> el prototipo de la web (de momento con datos de ejemplo)
.github/workflows/update-data.yml  -> automatización (sábados y domingos 23:00, hora de España)
```

## 1. Probarlo en local ahora mismo

```bash
python -m venv venv && source venv/bin/activate     # opcional pero recomendable
pip install -r requirements.txt
python scraper.py        # descarga y parsea todas las actas del grupo
python build_stats.py    # genera data/teams.json y data/players.json
```

La primera vez tardará varios minutos (hay ~1 segundo de pausa entre petición
y petición para no saturar el servidor de la FCF). Las siguientes veces solo
descarga los partidos que aún no tenga guardados en `data/matches/`.

Si algo falla al parsear una acta concreta, `scraper.py` lo avisa por
consola y sigue con las demás — no hace falta que todo funcione a la
primera para tener utilidad.

## 2. Posiciones de los jugadores

Edita `positions.json` a mano. El formato es:

```json
{
  "NOMBRE EXACTO COMO APARECE EN LA ACTA": "Portero"
}
```

Usa exactamente el mismo texto que aparece en la web de la FCF (mayúsculas
incluidas — es tal cual sale en las tablas de titulares). Los jugadores que
falten se mostrarán en la web con la posición "Sin definir".

## 3. Publicar la web gratis con GitHub Pages + dominio propio

1. Crea una cuenta en [github.com](https://github.com) si no tienes.
2. Crea un repositorio nuevo (puede ser público o privado) y sube todo el
   contenido de esta carpeta.
3. En el repo: **Settings → Pages → Build and deployment → Source: GitHub
   Actions**. Con esto, el workflow que ya está en
   `.github/workflows/update-data.yml` se encarga de publicar la carpeta
   `site/` automáticamente cada vez que se actualicen los datos.
4. **Dominio propio (sfcdatos.com):**
   - En el proveedor donde tengas registrado `sfcdatos.com` (Namecheap,
     GoDaddy, etc.), añade estos registros DNS:
     - 4 registros `A` apuntando a: `185.199.108.153`, `185.199.109.153`,
       `185.199.110.153`, `185.199.111.153`
     - Un registro `CNAME` para `www` apuntando a `tu-usuario.github.io`
   - En GitHub: **Settings → Pages → Custom domain** → escribe
     `www.sfcdatos.com` (o `sfcdatos.com`) y guarda. Marca también "Enforce
     HTTPS" en cuanto esté disponible (tarda unos minutos/horas en activarse).
5. Listo: a partir de ahí cualquier `git push` a `main` (incluidos los que
   hace el propio workflow automático) publica la web actualizada.

## 4. Actualización automática

El workflow ya está configurado para ejecutarse los **sábados y domingos a
las 23:00, hora de España** (robusto al cambio de horario CET/CEST — no hay
que tocarlo dos veces al año). Cada ejecución:
1. Descubre partidos nuevos desde `/calendari/...`
2. Parsea las actas que falten
3. Recalcula `teams.json` / `players.json`
4. Publica la web actualizada automáticamente

También puedes lanzarlo a mano en cualquier momento desde la pestaña
**Actions** del repositorio ("Run workflow").

## Próximo paso pendiente

`site/index.html` todavía usa datos de ejemplo (mock) para poder iterar el
diseño sin depender de tener ya toda la temporada descargada. Cuando
retomemos el diseño, el último paso es conectar el HTML a
`data/teams.json` / `data/players.json` en vez de al array `TEAMS` de
ejemplo — la forma de los datos ya es exactamente la misma, así que es un
cambio pequeño.
