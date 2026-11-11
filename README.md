# mp3sort

CLI en Python que recoge los `.mp3` de una carpeta de descargas, los renombra a `Artista - Título.mp3`, limpia sus tags y los mueve a una carpeta destino plana. Antes de tocar nada enseña una vista previa y tú decides qué se aplica.

## Objetivo

Las descargas llegan con nombres sucios (`Lumen - Prisma - www.example.com.mp3`, `07. Nova Delta - Open Sky 122.mp3`) y tags con webs, comentarios y géneros basura. mp3sort deja cada fichero como `Artista - Título.mp3`, con tags coherentes, y marca con ⚠ todo lo dudoso para revisarlo a mano en lugar de adivinar.

## Cómo funciona

### Nombre (artista y título)

- Se parte de los tags `artist`/`title`; si faltan, o el título contiene `Artista - `, se saca del nombre de fichero (quita número de pista, `_` y `__`, grupo de release final tipo `-abc`).
- Se limpian webs (`www...`, `http...`, `algo.com/.net/.org/.ru/.info/.io`), `()` vacíos, `[corchetes]`, paréntesis duplicados y un BPM final (2-3 dígitos entre 70 y 180, p. ej. `Open Sky 122`).
- Cuando el nombre sale de los tags se conservan tal cual la capitalización, los separadores de artistas (`,` `&` `x`) y `feat.`/`ft`. Si sale de un nombre de fichero estilo scene (sin espacios) se pasa a mayúscula inicial por palabra, `_` pasa a espacio y `__` a `, `.
- En el nombre de fichero `/` y `:` pasan a `-`; el tag conserva el texto original.
- Mix/remix: la designación va entre paréntesis. Se reutiliza el grupo `(..)` del nombre de fichero, o se envuelven las frases `Original Mix`, `Extended Mix`, `Extended`, `Extended Version`, `Radio Edit`, `Club Mix`, `Dub Mix`. Un `<x> Remix` sin evidencia de paréntesis se deja y se marca ⚠ "remix sin paréntesis, revisar".

### Casos marcados ⚠ (no se aplican por defecto)

Tag y nombre de fichero no coinciden; ¿artista y título intercambiados?; falta o se añade un `(grupo)` respecto al nombre de fichero; sin tags (sacado del nombre) o sin artista/título; caracteres raros (`< > | * "`) o cualquier símbolo suelto entre espacios (p. ej. ` ? ` o ` ! `; solo se exceptúan `&` `+` `/` `-` y la `x`). Un `?` pegado a una palabra (`Where To Go?`) es válido; no se pueden leer los tags; duplicado dentro de la tanda; ya existe en destino.

### Tags

- `album`, `comment` y `genre` se vacían; `artist` y `title` se escriben limpios.
- Se borra entero el tag APEv2.
- **Traktor**: el frame privado `PRIV:TRAKTOR4` se conserva a propósito. Traktor puede guardar en ese bloque su propia copia del comentario y mostrarla aunque la etiqueta ya no lo tenga.
- El resto de frames ID3 queda intacto. Se escribe ID3 v2.3/v2.4 (el v2.2 se reescribe como v2.4) más ID3v1.

### Mover con seguridad

Copiar → escribir tags en la copia → verificar (tags leídos y duración sin cambios, sin APEv2) → borrar el original. Si algo falla se borra la copia y el original queda intacto. Nunca se sobrescribe: duplicados y conflictos en destino se saltan. El destino es plano, y se rechaza un destino dentro del origen (o al revés). Solo se procesan `.mp3` (recursivo); el resto queda en origen, igual que los ficheros ocultos que empiezan por `.`. Si el original no se puede borrar tras verificar la copia, quedan ambos y se cuenta aparte (`Copiados sin borrar original`).

## Instalación

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # mutagen, pytest
```

## Uso

```sh
.venv/bin/python mp3sort.py "<carpeta destino>"
.venv/bin/python mp3sort.py --source "<carpeta origen>" "<carpeta destino>"
```

El origen por defecto es `~/Soulseek Downloads/complete`. Si origen o destino no existen, error y no se hace nada.

Vista previa, una línea por fichero:

```
⚠   1  Lumen - Prisma - www.example.com.mp3 → Lumen - Prisma.mp3  320 kbps  [motivo]
  ✓ 2  ...
```

Columna ⚠, columna ✓ (seleccionado), original → propuesto (nombres de más de 50 caracteres se cortan con `…`), bitrate (kbps, `VBR` si aplica; `? kbps` si se desconoce) y motivos entre `[...]`. Al final, un resumen `N ok · M ⚠`. Los ⚠ empiezan sin seleccionar. El prompt `> ` va en su propia línea:

- números (`3,5` o `3 5`): alterna incluir/excluir esas líneas;
- Enter: aplica los seleccionados;
- `q` (o fin de entrada/EOF): salir sin hacer nada.

Un fichero sin nombre propuesto no se puede incluir.

## Tests y feedback

```sh
.venv/bin/pytest
```

- `tests/fixtures/golden.csv` tiene casos con nombres inventados (`filename,tag_artist,tag_title,expected_filename,expected_flagged`). Es la vía de feedback: añade una fila por cada caso mal resuelto.
- Los datos reales viven solo en local, en `tests/fixtures/local/` y `tests/fixtures/audio/` (ambas en `.gitignore`). Los audios de prueba se generan con `tools/make_audio_fixtures.sh <carpeta>`; los tests que los necesitan se saltan si no están.
- Ningún test toca carpetas reales: trabajan en `tmp_path` o sobre copias.

## Herramientas

- `tools/extract_cases.py <carpeta>...`: lee los `.mp3` y vuelca nombre y tags a `tests/fixtures/local/cases.json` (local).
- `tools/report.py`: aplica las reglas a `cases.json` y escribe `report/report.md` (local) con los ⚠ primero.
- `tools/make_audio_fixtures.sh <carpeta>`: copia truncada (3 MB) de los 4 primeros `.mp3` a `tests/fixtures/audio/`.
- `tools/make_sandbox.sh <carpeta>...`: recrea `sandbox/` con `sandbox/complete` (copia de las carpetas dadas) y `sandbox/dest`, para probar sin riesgo. Solo borra un `sandbox/` que tenga el fichero marcador `.mp3sort-sandbox`.

## Limitaciones v1

- Solo `.mp3`; sin Discogs ni otras fuentes de metadatos.
- Interfaz solo de terminal, mensajes en español.
- Un `<x> Remix` sin paréntesis no se corrige solo: se marca para revisión.
- Las reglas son heurísticas; los casos dudosos se marcan ⚠ en lugar de resolverse.
- Próximo paso: una GUI (aún no construida).
