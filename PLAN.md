# GeoForm — plan

Modelador geológico a partir de sondajes: superficies implícitas, volúmenes y estimación de leyes.

## Stack
Python 3.11 · `sqlite3` (stdlib) · NumPy/SciPy · PyVista/VTK (visor 3D, marching cubes) · PySide6 ·
matplotlib · PyInstaller.

## Fases
1. Datos/I-O: schema SQLite + importadores CSV ✔
2. Núcleo: desurvey → modelo implícito (estratigrafía, fallas, intrusivos) → block model (kriging) → volumen/tonelaje ✔
3. App (GUI) + empaquetado `.exe` ✔ · `.dmg` pendiente (CI)
4. Verificación numérica con dataset sintético ✔

## Schema SQLite (especificación canónica)
```
collars  (hole_id PK, x, y, z, max_depth, azimuth, dip)
surveys  (hole_id, depth, azimuth, dip)              PK(hole_id, depth)
intervals(id PK, hole_id, from_depth, to_depth, lithology)
assays   (id PK, hole_id, from_depth, to_depth, element, value)
```

## Pendiente
- Grade shell por ley de corte (dominio no litológico).
- Fallas curvas / desde superficies digitalizadas.
- Pliegues volcados (contactos no 2.5D).
- `.dmg` para macOS y tipografía Inter incluida en el paquete.
