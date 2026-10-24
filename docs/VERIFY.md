# Verificación

Cada módulo trae un `demo()` con resultado conocido. Se corre con `python -m geoform.<módulo>`.

| Módulo | Qué comprueba |
|---|---|
| `desurvey` | pozo vertical y horizontal: coordenadas exactas |
| `implicit` | esfera unitaria desde puntos: radio de la malla en [0.7, 1.3] |
| `model` | plano conocido desde pozos verticales e inclinados: residuo < 0.5 m |
| `assemble` | 3 capas planas: volúmenes exactos por conteo de vóxeles; truncamiento por erosión |
| `kriging` | IDW constante y lineal; kriging exacto en las muestras |
| `block_model` | campo constante: estimación exacta |
| `grade` | compositado ponderado por largo y huecos (NaN) |
| `verify` | pipeline completo CSV → volúmenes exactos (32 000 / 48 000 / 240 000 m³) |
| `topography` | DEM sintético: el pico queda donde se puso |
| `estimation` | variograma de un campo con alcance conocido; curva ley-tonelaje |
| `export` | DXF de un cubo = 12 triángulos |
| `geomodel` | yacimiento sintético (falla + pórfido): acierto litológico > 85 % (≈96 %) |
| `project` | pipeline completo + guardar/abrir `.geoform` |

Además: `python -m tests.test_db_import` (schema e importadores con validación) y
`python -m geoform --smoke-gui` (construye la GUI, calcula el demo y sale).
