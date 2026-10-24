"""Perfil 2D: corte vertical del modelo con sondajes, superficies de contacto y trazado
de contactos a mano (clic). Los puntos trazados van a cfg["picks"] y entran a la
interpolación del techo de la unidad al recalcular (F5).
"""
import numpy as np
from PySide6 import QtCore, QtWidgets

from . import scene, theme


def section_grid(model, axis, pos, n=260):
    """Malla (h, elev) del perfil y puntos 3D en coordenadas del motor (z = -elev).
    axis 0 = perfil E-O (Y fijo, eje horizontal X); 1 = N-S (X fijo, eje horizontal Y)."""
    lo, hi = np.array(model.grid.bounds).reshape(3, 2).T
    h = np.linspace(lo[axis], hi[axis], n)
    elev = np.linspace(-hi[2], -lo[2], n)
    H, E = np.meshgrid(h, elev)
    P = np.empty((H.size, 3))
    P[:, axis], P[:, 1 - axis], P[:, 2] = H.ravel(), pos, -E.ravel()
    return H, E, P


def hole_traces(project, axis, pos, tol):
    """[(h, elev, lith)] tramos de sondaje a menos de `tol` m del plano del perfil."""
    from .model import _point_at_depth, hole_path

    out = []
    for hid, ints in project.intervals.items():
        x, y, z, az, dip = project.collars[hid]
        mds, path = hole_path(x, y, z, az, dip, project.surveys.get(hid, []))
        for f, t, lith in ints:
            q = np.array([_point_at_depth(mds, path, d) for d in np.linspace(f, t, max(2, int((t - f) / 2)))])
            near = np.abs(q[:, 1 - axis] - pos) < tol
            if near.any():
                out.append((q[near, axis], -q[near, 2], lith))
    return out


class VolumeDialog(QtWidgets.QDialog):
    """Volumen de roca entre dos superficies elegidas."""

    def __init__(self, surfaces, parent):
        super().__init__(parent)
        self.setWindowTitle("Volumen entre superficies")
        f = QtWidgets.QFormLayout(self)
        self.name = QtWidgets.QLineEdit("Volumen 1")
        self.top, self.bottom = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.top.addItems(surfaces)
        self.bottom.addItems(surfaces)
        self.bottom.setCurrentIndex(len(surfaces) - 1)
        f.addRow("Nombre", self.name)
        f.addRow("Superficie techo", self.top)
        f.addRow("Superficie base", self.bottom)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        if self.top.currentText() == self.bottom.currentText() or not self.name.text().strip():
            QtWidgets.QMessageBox.warning(self, "GeoForm", "Elige un nombre y dos superficies distintas.")
            return
        self.accept()

    def value(self):
        return {"name": self.name.text().strip(), "top": self.top.currentText(), "bottom": self.bottom.currentText()}


class SectionView(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        bar = QtWidgets.QHBoxLayout()
        self.axis = QtWidgets.QComboBox()
        self.axis.addItems(["Perfil Este-Oeste (Y fijo)", "Perfil Norte-Sur (X fijo)"])
        self.pos = QtWidgets.QSlider(QtCore.Qt.Horizontal, minimum=0, maximum=100, value=50)
        self.pos.setMinimumWidth(180)
        self.pos_label = QtWidgets.QLabel("", objectName="Muted")
        self.tol = QtWidgets.QDoubleSpinBox(minimum=2, maximum=200, value=25, suffix=" m", decimals=0)
        self.tol.setToolTip("Sondajes a menos de esta distancia del perfil")
        self.pick = QtWidgets.QToolButton(checkable=True, text="Trazar contacto")
        self.pick.setIcon(theme.icon("pen"))
        self.pick.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.pick.setToolTip("Clic en el perfil = punto de contacto del techo de la unidad elegida")
        self.unit = QtWidgets.QComboBox()
        undo = QtWidgets.QPushButton("Deshacer")
        clear = QtWidgets.QPushButton("Borrar trazos")
        vol = QtWidgets.QPushButton("Volumen entre superficies…", objectName="Primary")
        for w in (self.axis, QtWidgets.QLabel("Posición"), self.pos, self.pos_label, QtWidgets.QLabel("Ancho"),
                  self.tol, self.pick, self.unit, undo, clear):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(vol)
        v.addLayout(bar)
        self.fig, self.canvas = self.win._figure(10, 6)
        v.addWidget(self.canvas, 1)
        self.hint = QtWidgets.QLabel("", objectName="Muted")
        v.addWidget(self.hint)

        self.axis.currentIndexChanged.connect(self.draw)
        self.pos.sliderReleased.connect(self.draw)  # redibujar al soltar, no en cada paso
        self.pos.valueChanged.connect(lambda _: None if self.pos.isSliderDown() else self.draw())
        self.tol.valueChanged.connect(self.draw)
        undo.clicked.connect(self._undo)
        clear.clicked.connect(self._clear_picks)
        vol.clicked.connect(self._new_volume)
        self.canvas.mpl_connect("button_press_event", self._click)
        self._history = []

    # -- datos ----------------------------------------------------------------------
    def refresh(self):
        p = self.win.project
        self.unit.clear()
        self.unit.addItems(p.strat[1:])
        self.draw()

    def _plane(self):
        m = self.win.project.model
        ax = self.axis.currentIndex()
        lo, hi = np.array(m.grid.bounds).reshape(3, 2).T
        pos = lo[1 - ax] + (hi[1 - ax] - lo[1 - ax]) * self.pos.value() / 100
        return ax, pos

    def draw(self):
        from matplotlib.patches import Patch

        p = self.win.project
        if p is None or p.model is None:
            return
        m, (ax_i, pos) = p.model, self._plane()
        self.pos_label.setText(f"{'Y' if ax_i == 0 else 'X'} = {pos:,.0f}")
        H, E, P = section_grid(m, ax_i, pos, n=420)
        self.fig.clear()
        ax = self.fig.add_subplot()
        ax.set_facecolor("#1a2230")
        # cada unidad como polígono vectorial (contorno 0 de su campo): bordes suaves, sin píxeles
        for u in p.units:
            f = m.field_at(m.solids[u], P).reshape(H.shape)
            if f.max() > 0:
                ax.contourf(H, E, f, levels=[0.0, f.max() + 1], colors=[scene.unit_color(p, u)], alpha=0.92, antialiased=True)
                ax.contour(H, E, f, levels=[0.0], colors=["#0f1620"], linewidths=0.7)
        topo = m.field_at(m.surfaces["Topografía"], P).reshape(H.shape)
        ax.contour(H, E, topo, levels=[0.0], colors=["#f1f5f9"], linewidths=1.4)
        for fv in m.fault_values:
            ax.contour(H, E, m.field_at(fv, P).reshape(H.shape), levels=[0.0], colors=["#f43f5e"],
                       linewidths=1.5, linestyles="dashed")
        for name, field in m.custom.items():
            ax.contour(H, E, m.field_at(field, P).reshape(H.shape), levels=[0.0], colors=["#fbbf24"],
                       linewidths=1.8, linestyles="dotted")
        for h, e, lith in hole_traces(p, ax_i, pos, self.tol.value()):
            c = scene.unit_color(p, lith) if lith in p.units else "#8b98a8"
            ax.plot(h, e, color="#e2e8f0", lw=3.4, solid_capstyle="butt", zorder=3)  # borde claro: el sondaje se lee sobre su unidad
            ax.plot(h, e, color=c, lw=2.0, solid_capstyle="butt", zorder=4)
        for unit, pts in p.cfg["picks"].items():
            q = np.asarray(pts, float).reshape(-1, 3)
            q = q[np.abs(q[:, 1 - ax_i] - pos) < self.tol.value()]
            if len(q) and unit in p.units:
                ax.scatter(q[:, ax_i], q[:, 2], s=34, marker="D", color=scene.unit_color(p, unit), edgecolor="white",
                           linewidth=1.0, zorder=6)
        ax.set_xlabel("Este X (m)" if ax_i == 0 else "Norte Y (m)")
        ax.set_ylabel("Elevación (m)")
        ax.set_aspect("equal")
        ax.set_xlim(H.min(), H.max())
        ax.set_ylim(E.min(), E[topo > 0].max() + 15)  # recorta el aire sobre el terreno
        ax.grid(True, color="#ffffff", alpha=0.08, lw=0.6)
        ax.minorticks_on()
        ax.set_title(f"{self.axis.currentText().split(' (')[0]} · {self.pos_label.text()}", loc="left", fontsize=11)
        handles = [Patch(color=scene.unit_color(p, u), label=u) for u in p.units]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8,
                  title="Unidades", title_fontsize=8)
        self.canvas.draw_idle()
        n = sum(len(v) for v in p.cfg["picks"].values())
        self.hint.setText(f"Línea blanca = topografía · roja discontinua = falla · ámbar = volúmenes del usuario · "
                          f"{n} puntos trazados. Activa «Trazar contacto» y haz clic; F5 recalcula las mallas.")

    # -- edición --------------------------------------------------------------------
    def _click(self, ev):
        p = self.win.project
        if not self.pick.isChecked() or ev.inaxes is None or ev.button != 1 or not self.unit.currentText():
            return
        ax_i, pos = self._plane()
        xy = [ev.xdata, pos] if ax_i == 0 else [pos, ev.xdata]
        unit = self.unit.currentText()
        p.cfg["picks"].setdefault(unit, []).append([round(xy[0], 2), round(xy[1], 2), round(ev.ydata, 2)])
        self._history.append(unit)
        self.win.log(f"Contacto trazado (techo {unit}): {xy[0]:,.1f}, {xy[1]:,.1f}, {ev.ydata:,.1f}")
        self.draw()

    def _undo(self):
        if self._history:
            u = self._history.pop()
            self.win.project.cfg["picks"][u].pop()
            self.draw()

    def _clear_picks(self):
        if QtWidgets.QMessageBox.question(self, "GeoForm", "¿Borrar todos los contactos trazados?") \
                == QtWidgets.QMessageBox.Yes:
            self.win.project.cfg["picks"] = {}
            self._history.clear()
            self.draw()

    def _new_volume(self):
        p = self.win.project
        if p is None or p.model is None:
            return
        d = VolumeDialog(list(p.model.surfaces), self)
        if d.exec():
            vols = [v for v in p.cfg["volumes"] if v["name"] != d.value()["name"]]
            p.cfg["volumes"] = vols + [d.value()]
            self.win.log(f"Volumen {d.value()['name']}: {d.value()['top']} → {d.value()['bottom']}")
            self.win.rebuild()
