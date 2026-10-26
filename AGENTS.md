# Instrucciones para quien trabaje en GeoForm (personas o agentes de IA)

La nota del proyecto es `docs/PROYECTO.md` (también es la nota de Obsidian del dueño). Léela antes de empezar: tiene arquitectura, comandos, parámetros, bitácora y pendientes.

Al terminar un cambio, en el mismo commit:
1. Agrega una línea en **Bitácora** (`- AAAA-MM-DD: qué cambió y por qué`).
2. Marca `[x]` o quita de **Pendientes** lo que resolviste y agrega lo nuevo que quede pendiente.
3. Si cambian comandos, archivos clave o parámetros, actualiza esas secciones.

La sección **Bitácora automática** la escribe la GitHub Action `nota.yml` en cada push a `main`: no la edites a mano.

Escribe en español. Pruebas: `python -m geoform.<módulo>` (cada módulo tiene un `demo()` con asserts).
