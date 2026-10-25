"""Capturas de cada pestaña de la GUI con el demo -> docs/img/gui_*.png  (python docs/gallery_gui.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6 import QtCore, QtWidgets  # noqa: E402

from geoform.gui import run  # noqa: E402
from geoform.project import demo_project  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
win = run(demo_project().load(), smoke=True)
win.showMaximized()
app = QtWidgets.QApplication.instance()


def wait(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


for i in range(win.tabs.count()):
    win.tabs.setCurrentIndex(i)
    wait(2500)  # deja que VTK / matplotlib terminen de dibujar
    name = win.tabs.tabText(i).lower().replace(" ", "_").replace("ó", "o").replace("í", "i")
    # grabWindow toma los píxeles de pantalla: win.grab() deja negros los visores VTK
    app.primaryScreen().grabWindow(win.winId()).save(os.path.join(OUT, f"gui_{i + 1}_{name}.png"))
    print(name)
