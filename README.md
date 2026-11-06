# One Pace en español para Stremio

Addon estático que reúne [One Pace](https://onepace.net) con sus subtítulos oficiales en español y, cuando existen, los videos con subtítulos o doblaje latino que publica el proyecto.

## Instalación

En Stremio ve a **Addons → Add addon** y pega:

```
https://nicoaran77.github.io/one-pace-espanol/manifest.json
```

La serie aparece en **Descubrir → Series → One Pace en español**. No aparece en el buscador, porque un sitio estático no puede responder búsquedas.

## Opciones de cada episodio

- **Torrent:** audio japonés. Elige los subtítulos en español en el reproductor.
- **Pixeldrain, subtítulos:** el video ya trae los subtítulos latinos. Puede tener límite diario.
- **Pixeldrain, doblaje:** doblaje latino, solo en los episodios que lo tienen.

## Actualización

Una tarea de GitHub Actions regenera el addon cada día con `scripts/build.py`. Si una fuente falla o devuelve muy pocos episodios, se conserva la versión publicada. `report.json` resume la última generación.

## Créditos

Los episodios, los subtítulos y el doblaje son trabajo del [equipo de One Pace](https://onepace.net) ([subtítulos](https://github.com/one-pace/one-pace-public-subtitles)). La lista de episodios se basa en los addons de [au2001](https://github.com/au2001/onepace-stremio) y [fedew04](https://github.com/fedew04/OnePaceStremio). Este repositorio no aloja video.
