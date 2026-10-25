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
        from pyvistaqt import QtInteractor

        self.ve = QtWidgets.QDoubleSpinBox(minimum=1, maximum=5, singleStep=0.5, value=1, decimals=1, prefix="V ×")
        self.ve.setToolTip("Exageración vertical del perfil")
        bar.insertWidget(6, self.ve)
        self.view = QtInteractor(self)  # perfil renderizado con VTK (como el corte de Leapfrog)
        v.addWidget(self.view, 1)
        self.view.track_click_position(self._click, side="left")
        self.hint = QtWidgets.QLabel("", objectName="Muted")
        v.addWidget(self.hint)

        self.axis.currentIndexChanged.connect(self.draw)
        self.pos.sliderReleased.connect(self.draw)  # redibujar al soltar, no en cada paso
        self.pos.valueChanged.connect(lambda _: None if self.pos.isSliderDown() else self.draw())
        self.tol.valueChanged.connect(self.draw)
        self.ve.valueChanged.connect(self.draw)
        undo.clicked.connect(self._undo)
        clear.clicked.connect(self._clear_picks)
        vol.clicked.connect(self._new_volume)
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

    def draw(self, keep_camera=False):
        """Corte ortogonal con VTK: caras de cada unidad, contactos finos, topografía, falla,
        sondajes cercanos con puntos de contacto, rótulos y marco del modelo."""
        import pyvista as pv

        p = self.win.project
        if p is None or p.model is None:
            return
        m, (ax_i, pos) = p.model, self._plane()
        self.pos_label.setText(f"{'Y' if ax_i == 0 else 'X'} = {pos:,.0f}")
        normal = (0.0, 1.0, 0.0) if ax_i == 0 else (1.0, 0.0, 0.0)
        origin = (0.0, pos, 0.0) if ax_i == 0 else (pos, 0.0, 0.0)
        toward = -1.0  # la cámara mira desde el lado negativo (sur / oeste)
        off = np.array(normal) * toward  # desplaza líneas hacia la cámara: siempre sobre las caras
        cam = self.view.camera_position if keep_camera and self.view.renderer.actors else None
        pl = self.view
        pl.clear()
        pl.set_background("#0b1636", top="#1d2c4f")
        g = scene.flip(m.grid)
        for u, face in scene.section_faces(p, normal, origin):
            pl.add_mesh(face, color=scene.unit_color(p, u), lighting=False, name=f"f:{u}")
            g.point_data["s"] = m.partition()[u]
            edge = g.slice(normal=normal, origin=origin).contour([0.0], scalars="s")
            if edge.n_points:
                pl.add_mesh(edge.translate(off * 0.5, inplace=False), color="#0b1636", line_width=1.2, opacity=0.7)
        for i, fv in enumerate(m.fault_values):  # campos en la grilla antes de cortar
            g.point_data[f"f{i}"] = fv
        for k, (name, field) in enumerate(m.custom.items()):
            g.point_data[f"c{k}"] = field
        sl = g.slice(normal=normal, origin=origin)
        topo = sl.contour([0.0], scalars="topo")
        if topo.n_points:
            pl.add_mesh(topo.translate(off, inplace=False), color="#f1f5f9", line_width=2.2)
        for i in range(len(m.fault_values)):
            tr = sl.contour([0.0], scalars=f"f{i}")
            if tr.n_points:
                pl.add_mesh(tr.translate(off, inplace=False), color="#ff5c8a", line_width=2.6)
        for k in range(len(m.custom)):
            tr = sl.contour([0.0], scalars=f"c{k}")
            if tr.n_points:
                pl.add_mesh(tr.translate(off, inplace=False), color="#fbbf24", line_width=2.0)
        # sondajes a menos de `ancho` del plano, proyectados sobre él
        pts, cols = [], []
        for h, e, lith in hole_traces(p, ax_i, pos, self.tol.value()):
            P3 = np.zeros((len(h), 3))
            P3[:, ax_i], P3[:, 1 - ax_i], P3[:, 2] = h, pos, e
            P3 += off * 2
            pl.add_mesh(pv.lines_from_points(P3), color="#e2e8f0", line_width=1.6, opacity=0.9)
            pts += [P3[0], P3[-1]]
            cols += [scene.unit_color(p, lith) if lith in p.units else "#8b98a8"] * 2
        if pts:
            cp = pv.PolyData(np.array(pts))
            cp["rgb"] = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in cols], np.uint8)
            pl.add_mesh(cp, scalars="rgb", rgb=True, point_size=7, render_points_as_spheres=True)
        for unit, q in p.cfg["picks"].items():
            q = np.asarray(q, float).reshape(-1, 3)
            q = q[np.abs(q[:, 1 - ax_i] - pos) < self.tol.value()]
            if len(q) and unit in p.units:
                pl.add_mesh(pv.PolyData(q + off * 3), color=scene.unit_color(p, unit), point_size=13,
                            render_points_as_spheres=True)
        # rótulos en el punto más interior de cada unidad
        H, E, P = section_grid(m, ax_i, pos, n=160)
        lab_pts, labs = [], []
        for u in p.units:
            f = m.field_at(m.solids[u], P)
            if (f > 0).sum() > 25:
                k = int(np.argmax(f))
                q = np.zeros(3)
                q[ax_i], q[1 - ax_i], q[2] = H.flat[k], pos, E.flat[k]
                lab_pts.append(q + off * 4)
                labs.append(u)
        if labs:
            pl.add_point_labels(np.array(lab_pts), labs, font_size=13, text_color="white", bold=True,
                                shape=None, show_points=False, always_visible=True, font_family="arial",
                                shadow=True)
        b = np.array(m.grid.bounds).reshape(3, 2)
        top = float(E[m.field_at(m.surfaces["Topografía"], P).reshape(H.shape) > 0].max())
        a0, a1 = b[ax_i]
        frame = np.zeros((5, 3))
        frame[:, ax_i] = [a0, a1, a1, a0, a0]
        frame[:, 1 - ax_i] = pos
        frame[:, 2] = [E.min(), E.min(), top, top, E.min()]
        pl.add_mesh(pv.lines_from_points(frame + off * 2), color="#d946ef", line_width=1.6)
        pl.set_scale(zscale=self.ve.value())
        pl.enable_parallel_projection()
        pl.enable_anti_aliasing("fxaa")
        pl.add_text(f"{self.axis.currentText().split(' (')[0]}  ·  {self.pos_label.text()}  ·  ancho "
                    f"{self.tol.value():.0f} m  ·  V ×{self.ve.value():g}", position="upper_left", font_size=8,
                    color="#e2e8f0", font="arial")
        if cam:
            pl.camera_position = cam
        else:
            c = np.zeros(3)
            c[ax_i], c[1 - ax_i], c[2] = (a0 + a1) / 2, pos, (E.min() + top) / 2 * self.ve.value()
            pl.camera.focal_point = c
            pl.camera.position = c + np.array(normal) * toward * 5000
            pl.camera.up = (0, 0, 1)
            pl.reset_camera()
            wpx, hpx = max(self.view.width(), 1), max(self.view.height(), 1)
            half_h = (top - E.min()) * self.ve.value() / 2
            half_w = (a1 - a0) / 2
            pl.camera.parallel_scale = 1.15 * max(half_h, half_w * hpx / wpx)  # la sección llena la vista
        pl.render()
        n = sum(len(v) for v in p.cfg["picks"].values())
        self.hint.setText(f"Rueda = zoom · clic derecho/medio = desplazar · blanco = topografía · rosa = falla · "
                          f"ámbar = volúmenes · magenta = límite del modelo · {n} puntos trazados. "
                          f"«Trazar contacto» + clic; F5 recalcula.")

    # -- edición --------------------------------------------------------------------
    def _click(self, xyz):
        """Clic en el perfil (coordenadas de mundo en elevación) -> punto de contacto en el plano."""
        p = self.win.project
        if not self.pick.isChecked() or not self.unit.currentText() or p is None or p.model is None:
            return
        ax_i, pos = self._plane()
        q = list(map(float, xyz))
        q[2] /= self.ve.value()  # deshace la exageración vertical
        q[1 - ax_i] = pos
        unit = self.unit.currentText()
        p.cfg["picks"].setdefault(unit, []).append([round(v, 2) for v in q])
        self._history.append(unit)
        self.win.log(f"Contacto trazado (techo {unit}): {q[0]:,.1f}, {q[1]:,.1f}, {q[2]:,.1f}")
        self.draw(keep_camera=True)

    def _undo(self):
        if self._history:
            u = self._history.pop()
            self.win.project.cfg["picks"][u].pop()
            self.draw(keep_camera=True)

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
