---
tipo: proyecto
categoria: Modelamiento y estudio
estado: activo
tecnologia: Python, PySide6, PyVista, SciPy
carpeta: "/Users/claudiofranciscomunozrubilar/Desktop/Proyectos/GeoForm"
repositorio: "https://github.com/clfranmunoz-bot/GeoForm"
---
# GeoForm
#python #geologia #3d #leapfrog

**Temas:** [[Python]] · [[Geología]] · [[Sondajes]]

Modelador geológico 3D de escritorio, pensado como alternativa a **Leapfrog Geo**: modelo implícito desde sondajes, fallas, intrusivos y vetas, estimación de recursos (kriging, simulación), pit óptimo y exportación. Es distinto de [[GEO-MODELER]] (otro proyecto, carpeta `Modelador`).

**Código:** [Abrir carpeta](file:///Users/claudiofranciscomunozrubilar/Desktop/Proyectos/GeoForm) · **GitHub:** clfranmunoz-bot/GeoForm (rama `main`)
**App:** acceso directo «GeoForm» en el escritorio → `GeoForm/dist/GeoForm.app`

## Cómo trabajar con el proyecto
- Entorno: `.venv/` (Python 3.11, creado el 2026-10-26, ignorado por git). Si falta: `python3.11 -m venv .venv && .venv/bin/pip install -e . pytest pyinstaller`.
- Abrir la app desde código: `.venv/bin/python -m geoform` (abre el demo, un pórfido Cu sintético).
- Reporte en consola: `.venv/bin/python -m geoform --report`.
- Pruebas: cada módulo tiene un `demo()` con asserts → `.venv/bin/python -m geoform.<módulo>` (geomodel, estimation, project, export, kriging, pit, grade, implicit, model). No hay tests pytest; `tests/test_scenarios.py` es un script (`python -m tests.test_scenarios`).
- GUI sin ventana (test): `--smoke-gui`. Captura 3D: `--screenshot out.png --section`.
- **Reconstruir la app** (el acceso directo NO se actualiza solo): `.venv/bin/pyinstaller --noconfirm --clean geoform.spec` → reemplaza `dist/GeoForm.app`; el alias del escritorio sigue apuntando ahí.
- Datos demo con verdad conocida: `geoform/synth.py` genera `geoform/data/`.

## Arquitectura (archivos clave)
| Archivo | Qué hace |
|---|---|
| `project.py` | `Project`: config `.geoform` (JSON) con `DEFAULTS`, pipeline `load → build → estimate → simulate`, reportes |
| `geomodel.py` | `GeoModel`: estratigrafía 2.5D (TPS), fallas planas por bloques, intrusivos RBF 3D, vetas (techo/piso sobre plano medio), sólidos por marching cubes; `aniso_matrix`, `fit_field` |
| `estimation.py` | compósitos por dominio, variograma (anidado, anisotropía 3D), kriging de bloques (kriging / idw / nearest), clasificación, `sgs` (simulación), `regularize` (SMU), envolventes de ley, swath, validación cruzada |
| `kriging.py` | kriging ordinario 3D local, con varianza, e IDW |
| `pit.py` | pit óptimo exacto (clausura máxima por flujo máximo, equivalente a Lerchs-Grossmann) |
| `scene.py` | capas 3D, slicer, `section_faces` (caras de corte) |
| `section2d.py` | pestaña Perfil 2D (trazado de contactos, volúmenes entre superficies) |
| `gui.py` | ventana principal, diálogo Parámetros, pestañas Variograma / Estadística / Recursos |
| `export.py` | DXF, OBJ, STL, PLY, TSurf, VTK; bloques CSV / Parquet (opcional) / VTK; reporte TXT |
| `geoform.spec`, `entry_point.py`, `vtk_constants_hook.py` | empaquetado PyInstaller para macOS |

Convenciones: coordenadas del motor con **z = profundidad = −elevación**; en los CSV la `z` del collar es elevación y el `dip` es negativo hacia abajo.

## Parámetros nuevos del proyecto (diálogo Parámetros)
- `method`: `kriging` | `idw` | `nearest` (vecino más cercano).
- `drift`: `linear` | `quadratic` (tendencia de los RBF del modelo geológico).
- `anisotropy`: `{bearing, plunge, ratios[3]}`; en intrusivos 3D, en contactos solo rumbo y razón en planta. `1,1,1` = isótropo.
- `simulations`: realizaciones SGS (0 = apagado, ~3 s cada una en el demo) → capa «Probabilidad SGS», tarjeta P10/P50/P90.
- `smu`: re-bloqueo `[n,n,n]` para la curva ley-tonelaje con dilución.
- `mesh_refinement`: 1 sin subdividir, 2 Loop, 3 Butterfly.

## Bitácora
- 2026-10-26: revisión completa del proyecto. Borrado código muerto (`sqlite_backend.py`, `validation.py`, FastRBF falso porque el paquete `fast-rbf` no existe, `lerchs_grossmann` duplicado, `grade_shells`, `probability_shell`, `cross_validate_detailed`, `swath_detailed`, `reblock_model`, `top_cut`, `decluster`, `infer/apply_fault_displacement`, ~700 líneas). Commit 91b78c7.
- 2026-10-26: conectada la simulación SGS (reescrita: la anterior no era secuencial ni normalizaba la meseta) y el re-bloqueo SMU a Project, GUI y escena.
- 2026-10-26: la ventana no cabía en pantalla (mínimo 1925 px por la barra del Perfil 2D y tarjetas KPI) → barra en dos filas y textos con salto de línea; mínimo 1273 px. Secciones 3D y 2D se veían escalonadas (capa por vóxel bajo las caras) → corte exacto por polígonos: cada unidad se recorta contra las demás por la diferencia de campos. Commit ac74cdb.
- 2026-10-26: exportación STL y PLY, método vecino más cercano, drift (lineal/cuadrático) y anisotropía en los RBF del modelo geológico; Exportar ya no falla sin pyarrow. App reconstruida y alias «GeoForm» creado en el escritorio. Commit dd38219 (subido a GitHub).

## Comparación con Leapfrog Geo (estado al 2026-10-26)
Fuente: informe operativo de Leapfrog (FastRBF, interpolantes, flujo, DSL de cálculos, salidas, Central/Evo).

**Ya cubierto:** flujo completo sondajes → compósitos/top-cut → modelo implícito → isosuperficies → bloques → salidas; fallas integradas (solo planas); envolventes de ley (RBF lineal); anisotropía en variograma, kriging y RBF geológicos; drift lineal y cuadrático; kriging, IDW y vecino más cercano; SGS; pit óptimo (Leapfrog no lo trae); mallas DXF/OBJ/STL/PLY/TSurf/VTK; bloques CSV/Parquet/VTK; swath, ley-tonelaje, reporte TXT.

**Ojo:** `COMPARATIVE_REPORT.md` (en el repo) exagera el avance: da por hechos FastRBF y kriging simple/universal, que **no existen**. Hay que corregirlo.

## Pendientes
### Esfuerzo bajo (siguiente sesión)
- [ ] Interpolante **esferoidal** (RBF de alcance finito: kernel propio con el modelo esférico).
- [ ] **Indicator RBF** para envolventes de ley (interpolar 0/1 sobre la ley de corte).
- [ ] **RBF local** (`neighbors=` en `fit_field`) para escalar a cientos de miles de puntos (sustituto práctico de FastRBF).
- [ ] Exportar grillas a **ESRI ASCII** (stdlib) y quizá GeoTIFF (requiere rasterio).
- [ ] Reporte **HTML/PDF** (matplotlib + reporte TXT ya existen).
- [ ] Drift constante (requiere kernel lineal; TPS exige grado ≥ 1).
- [ ] Corregir `COMPARATIVE_REPORT.md` al estado real.
### Esfuerzo medio
- [ ] Bloques en formato Surpac/Micromine (CSV con encabezado propio); Datamine y Vulcan son binarios cerrados.
- [ ] Fallas curvas (desde superficies digitalizadas).
- [ ] Pliegues volcados (hoy los contactos son 2.5D, sin z doble).
- [ ] Actualización incremental (caché de campos por unidad; hoy se recalcula todo).
- [ ] Bordes exteriores del bloque modelado se ven redondeados (suavizado Taubin de la malla).
- [ ] Kriging simple y universal.
### Esfuerzo alto (solo si hace falta)
- [ ] FastRBF real (descomposición de dominio + FGMRES, >1 M puntos).
- [ ] Lenguaje de cálculos tipo Leapfrog (`if`, `[x]`, `inside()`, `distance_to()`).
- [ ] Equivalente a Central/Evo/nube (versionado, API, colaboración); hoy: git + `.geoform` + Python.
- [ ] `.dmg` para macOS y tipografía Inter incluida en el paquete (de `PLAN.md`).

## Bitácora automática
Cada push a `main` agrega aquí una línea (GitHub Action `.github/workflows/nota.yml`), lo haga quien lo haga. Los pendientes y la bitácora de arriba los actualiza a mano quien cambie el proyecto (ver `AGENTS.md`).
<!-- commits -->
- 2026-10-26 · Claudio Francisco Muñoz Rubilar · `58a7a89` Nota del proyecto en docs/PROYECTO.md con bitácora automática por GitHub Action
