# One Pace en español para Stremio

Addon estático que reúne [One Pace](https://onepace.net) con sus subtítulos oficiales en español y, cuando existen, los videos con subtítulos o doblaje latino que publica el proyecto.

## Instalación

En Stremio ve a **Addons → Add addon** y pega:

```
https://nicoaran77.github.io/one-pace-espanol/manifest.json
```

La serie aparece en **Descubrir → Series → One Pace en español**, con una temporada por saga. Stremio solo muestra «Season N», así que el título de cada episodio indica su arco. No aparece en el buscador, porque un sitio estático no puede responder búsquedas.

| Temporada | Saga | Arcos |
|---|---|---|
| 1 | East Blue | Romance Dawn a Loguetown |
| 2 | Alabasta | Reverse Mountain a Alabasta |
| 3 | Skypiea | Jaya y Skypiea |
| 4 | Water 7 | Long Ring Long Land a Post-Enies Lobby |
| 5 | Thriller Bark | Thriller Bark |
| 6 | Guerra de Marineford | Sabaody a Post-War |
| 7 | Isla Gyojin | Return to Sabaody y Fishman Island |
| 8 | Dressrosa | Punk Hazard y Dressrosa |
| 9 | Cuatro Emperadores | Zou a Wano |
| 10 | Saga Final | Egghead |

## Opciones de cada episodio

- **Torrent:** elige «Español» en el menú de subtítulos. Algunos videos traen además pistas de audio y subtítulos propios.
- **Pixeldrain, subtítulos:** el video ya trae los subtítulos latinos. Puede tener límite diario.
- **Pixeldrain, doblaje:** doblaje latino, solo en los episodios que lo tienen.
- **Episodios aún sin español:** se incluyen con subtítulos en inglés para poder ver la serie seguida.

## Actualización

Una tarea de GitHub Actions regenera el addon cada día con `scripts/build.py`. Si una fuente falla o devuelve muy pocos episodios, se conserva la versión publicada. `report.json` resume la última generación.

## Créditos

Los episodios, los subtítulos y el doblaje son trabajo del [equipo de One Pace](https://onepace.net) ([subtítulos](https://github.com/one-pace/one-pace-public-subtitles)). La lista de episodios se basa en los addons de [au2001](https://github.com/au2001/onepace-stremio) y [fedew04](https://github.com/fedew04/OnePaceStremio). Este repositorio no aloja video.
