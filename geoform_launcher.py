"""Launcher para PyInstaller: los imports relativos de geoform.__main__ fallan
si se pasa como script. Este módulo importa el paquete por ruta absoluta."""
from geoform.__main__ import main

main()
