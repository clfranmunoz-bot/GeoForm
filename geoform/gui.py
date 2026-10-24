"""GUI de GeoForm: árbol de proyecto | escena 3D | capas | inspector.

Pestañas centrales: Escena 3D, Perfil 2D, Variograma, Recursos. El cálculo del modelo
corre en un hilo aparte (QThread) con un velo de progreso sobre el área central.
"""
import os

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from pyvistaqt import QtInteractor

from . import scene, theme
from .project import Project
from .scene import DEFAULT_ON


STYLES = ["Sólido", "Sólido + aristas", "Malla (alambre)", "Translúcido", "Puntos"]


class Overlay(QtWidgets.QWidget):
    """Velo con progreso sobre el área central mientras corre el cálculo."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Overlay")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setAlignment(QtCore.Qt.AlignCenter)
        box = QtWidgets.QFrame(objectName="Card")
        box.setFixedWidth(440)
        b = QtWidgets.QVBoxLayout(box)
        b.setContentsMargins(28, 24, 28, 24)
        b.setSpacing(12)
        b.addWidget(QtWidgets.QLabel("Calculando modelo", objectName="OverlayTitle"))
        self.msg = QtWidgets.QLabel("", objectName="Muted")
        self.msg.setWordWrap(True)
        b.addWidget(self.msg)
        b.addWidget(QtWidgets.QProgressBar(minimum=0, maximum=0, textVisible=False))
        lay.addWidget(box)
        self.hide()

    def show_over(self, text):
        self.msg.setText(text)
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()

    def eventFilter(self, obj, ev):  # sigue el tamaño del padre
        if ev.type() == QtCore.QEvent.Resize:
            self.setGeometry(obj.rect())
        return False


def card(label, value, sub="", accent=None):
    f = QtWidgets.QFrame(objectName="Card")
    v = QtWidgets.QVBoxLayout(f)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(2)
    v.addWidget(QtWidgets.QLabel(label.upper(), objectName="KpiLabel"))
    val = QtWidgets.QLabel(value, objectName="KpiValue")
    if accent:
        val.setStyleSheet(f"color: {accent};")
    v.addWidget(val)
    v.addWidget(QtWidgets.QLabel(sub, objectName="KpiSub"))
    return f


def spacer(w):
    x = QtWidgets.QWidget()
    x.setFixedWidth(w)
    return x


class BuildThread(QtCore.QThread):
    done = QtCore.Signal(object)
    message = QtCore.Signal(str)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def run(self):
        try:
            self.project.log = self.message.emit
            self.project.load().build()
            self.done.emit(None)
        except Exception as e:  # el error se muestra en la consola, la GUI sigue viva
            self.done.emit(e)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, project=None):
        super().__init__()
        self.resize(1680, 1000)
        self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(theme.CHECK), "geoform.ico")))
        self.project = project
        self.layer_defs, self.base_kw, self.actors = {}, {}, {}
        self.styles = {}  # key -> (estilo, sombreado) elegido en la barra de capas; sobrevive a render_all
        self.visible = set()
        self.clip = None
        self._thread = None

        # escena central + pestañas
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QtCore.QSize(16, 16))
        self.plotter = QtInteractor(self)
        self.tabs.addTab(self.plotter, theme.icon("scene"), "Escena 3D")
        from .section2d import SectionView
        self.section = SectionView(self)
        self.tabs.addTab(self.section, theme.icon("section"), "Perfil 2D")
        from .correlation import CorrelationView
        from .stats_view import StatsView
        self.correlation = CorrelationView(self)
        self.tabs.addTab(self.correlation, theme.icon("drill"), "Correlación")
        self.vario_tab = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(self.vario_tab).setContentsMargins(20, 16, 20, 16)
        self.tabs.addTab(self.vario_tab, theme.icon("vario"), "Variograma")
        self.stats = StatsView(self)
        self.tabs.addTab(self.stats, theme.icon("report"), "Estadística")
        self.report_tab = QtWidgets.QScrollArea(widgetResizable=True, frameShape=QtWidgets.QFrame.NoFrame)
        self.tabs.addTab(self.report_tab, theme.icon("report"), "Recursos")
        self.setCentralWidget(self.tabs)
        self.overlay = Overlay(self.tabs)
        self.tabs.installEventFilter(self.overlay)

        # árbol de proyecto
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QtCore.QSize(16, 16))
        self.tree.itemChanged.connect(self._tree_toggled)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self._dock("Proyecto", self.tree, QtCore.Qt.LeftDockWidgetArea).setMinimumWidth(290)

        # capas visibles + consola (pestañas en el panel inferior)
        self.shape_list = QtWidgets.QListWidget()
        d_layers = self._dock("Capas", self.shape_list, QtCore.Qt.BottomDockWidgetArea)
        self.console = QtWidgets.QPlainTextEdit(readOnly=True, objectName="Console")
        d_console = self._dock("Consola", self.console, QtCore.Qt.BottomDockWidgetArea)
        self.tabifyDockWidget(d_layers, d_console)
        d_layers.raise_()

        self._dock("Inspector", self._build_props(), QtCore.Qt.RightDockWidgetArea).setMinimumWidth(290)

        self._build_toolbar()
        self.zlabel = QtWidgets.QLabel("Z ×1.0")
        self.cam_label = QtWidgets.QLabel("")
        self.status_dot = QtWidgets.QLabel("Listo")
        self.statusBar().addWidget(self.status_dot)
        self.statusBar().addPermanentWidget(self.cam_label)
        self.statusBar().addPermanentWidget(self.zlabel)
        self.plotter.iren.add_observer("EndInteractionEvent", lambda *_: self._update_cam_label())
        if project is not None:
            self.rebuild()

    # -- construcción de la UI ------------------------------------------------------
    def _dock(self, title, widget, area):
        d = QtWidgets.QDockWidget(title, self)
        d.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        d.setWidget(widget)
        d.setObjectName(title)
        self.addDockWidget(area, d)
        return d

    def _build_toolbar(self):
        tb = QtWidgets.QToolBar("Header", objectName="Header")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        logo = QtWidgets.QLabel()
        logo.setPixmap(theme.icon("logo", theme.ACCENT, 24).pixmap(24, 24))
        tb.addWidget(spacer(8))
        tb.addWidget(logo)
        tb.addWidget(QtWidgets.QLabel(" GeoForm", objectName="Brand"))
        tb.addWidget(spacer(12))
        self.chip = QtWidgets.QLabel("", objectName="ProjectChip")
        tb.addWidget(self.chip)
        tb.addWidget(spacer(20))

        def btn(text, ic, fn, tip, primary=False):
            b = QtWidgets.QToolButton()
            b.setIcon(theme.icon(ic, "#04201c" if primary else theme.TEXT2))
            b.setText(text)
            b.setToolTip(tip)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(fn)
            tb.addWidget(b)

        btn("Nuevo", "new", self.new_project, "Nuevo proyecto desde CSV")
        btn("Abrir", "open", self.open_project, "Abrir proyecto .geoform (Ctrl+O)")
        btn("Guardar", "save", self.save_project, "Guardar proyecto (Ctrl+S)")
        btn("Parámetros", "params", self.edit_parameters, "Estratigrafía, fallas, dominio y grillas")
        btn("Exportar", "export", self.export, "DXF / OBJ / block model CSV / reporte")
        btn("Captura", "camera", self.screenshot, "Guardar la vista 3D como PNG")
        btn("Fondo", "iso", self._toggle_bg, "Alternar escena clara / oscura")
        QtGui.QShortcut(QtGui.QKeySequence.Open, self, self.open_project)
        QtGui.QShortcut(QtGui.QKeySequence.Save, self, self.save_project)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, self.rebuild)

        stretch = QtWidgets.QWidget()
        stretch.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(stretch)
        seg = QtWidgets.QFrame(objectName="SegGroup")
        h = QtWidgets.QHBoxLayout(seg)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(0)
        for text, ic, view in [("Planta", "plan", (180, 89.9)), ("Norte", "north", (0, 0.1)),
                               ("Este", "east", (90, 0.1)), ("3D", "iso", (225, 30))]:
            b = QtWidgets.QToolButton(objectName="Seg")
            b.setIcon(theme.icon(ic))
            b.setText(text)
            b.setToolTip(f"Vista {text}")
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.clicked.connect(lambda _=False, v=view: self.set_view(v))
            h.addWidget(b)
        tb.addWidget(seg)
        tb.addWidget(spacer(14))
        tb.addWidget(QtWidgets.QLabel("Z ×", objectName="Muted"))
        self.zscale = QtWidgets.QDoubleSpinBox(minimum=0.5, maximum=5.0, singleStep=0.5, value=1.0, decimals=1)
        self.zscale.setFixedWidth(52)
        self.zscale.setToolTip("Exageración vertical")
        self.zscale.valueChanged.connect(self._set_zscale)
        tb.addWidget(self.zscale)
        tb.addWidget(spacer(14))
        btn("Recalcular", "run", self.rebuild, "Recalcular modelo y estimación (F5)", primary=True)
        tb.addWidget(spacer(8))

    def _build_props(self):
        w = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(w)
        f.setContentsMargins(16, 8, 16, 12)
        f.setVerticalSpacing(10)
        f.addRow(QtWidgets.QLabel("SELECCIÓN", objectName="SectionTitle"))
        self.prop_title = QtWidgets.QLabel("Ninguna capa", objectName="PropTitle")
        f.addRow(self.prop_title)
        self.prop_info = QtWidgets.QLabel("Marca una capa del proyecto para ver sus propiedades.", objectName="Muted")
        self.prop_info.setWordWrap(True)
        f.addRow(self.prop_info)
        f.addRow(QtWidgets.QLabel("SLICER", objectName="SectionTitle"))
        self.slice_on = QtWidgets.QCheckBox("Activar corte")
        self.slice_on.toggled.connect(self._apply_slicer)
        f.addRow(self.slice_on)
        self.slice_dir = QtWidgets.QComboBox()
        self.slice_dir.addItems(["Norte-Sur (corte en Y)", "Este-Oeste (corte en X)", "Horizontal (Z)"])
        self.slice_dir.currentIndexChanged.connect(self._apply_slicer)
        f.addRow("Orientación", self.slice_dir)
        self.slice_pos = QtWidgets.QSlider(QtCore.Qt.Horizontal, minimum=0, maximum=100, value=50)
        self.slice_pos.sliderReleased.connect(self._apply_slicer)
        f.addRow("Posición", self.slice_pos)
        self.slice_flip = QtWidgets.QCheckBox("Invertir lado")
        self.slice_flip.toggled.connect(self._apply_slicer)
        f.addRow(self.slice_flip)
        return w

    # -- proyecto -------------------------------------------------------------------
    def log(self, msg):
        self.console.appendPlainText(str(msg))

    def _status(self, color, text):
        self.status_dot.setText(f"<span style='color:{color}'>●</span>&nbsp; {text}")

    def rebuild(self):
        if self.project is None or (self._thread is not None and self._thread.isRunning()):
            return
        self.setWindowTitle(f"GeoForm — {self.project.cfg['name']}")
        self.chip.setText(self.project.cfg["name"])
        self._status(theme.AMBER, "Calculando…")
        self.overlay.show_over("Interpolando contactos, fallas e intrusivos y estimando leyes por kriging.")
        self._thread = BuildThread(self.project)
        self._thread.message.connect(self.log)
        self._thread.message.connect(self.overlay.msg.setText)
        self._thread.done.connect(self._built)
        self._thread.start()

    def _built(self, err):
        self.overlay.hide()
        self._status(theme.ACCENT if err is None else theme.RED, "Modelo actualizado" if err is None else "Error")
        if err is not None:
            self.log(f"ERROR: {err}")
            QtWidgets.QMessageBox.critical(self, "GeoForm", str(err))
            return
        p = self.project
        self.setWindowTitle(f"GeoForm — {p.cfg['name']}  [{p.path or 'sin guardar'}]")
        self.log(p.report())
        self.layer_defs = {k: (g, lab, b) for k, g, lab, b in scene.layers(p)}
        self.resizeDocks([self.findChild(QtWidgets.QDockWidget, "Capas")], [170], QtCore.Qt.Vertical)
        self.base_kw.clear()
        self.visible = {k for k in self.layer_defs if k.startswith(DEFAULT_ON)}
        self._fill_tree()
        self.render_all()
        scene.set_view(self.plotter, p)
        self.section.refresh()
        self.correlation.refresh()
        self.stats.refresh()
        self._fill_variogram()
        self._fill_report()

    def _fill_tree(self):
        p = self.project
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}

        def group(name):
            if name not in groups:
                groups[name] = QtWidgets.QTreeWidgetItem([name])
                groups[name].setIcon(0, theme.icon(theme.GROUP_ICON.get(name, "folder"), theme.ACCENT))
                fnt = groups[name].font(0)
                fnt.setWeight(QtGui.QFont.DemiBold)
                groups[name].setFont(0, fnt)
                self.tree.addTopLevelItem(groups[name])
            return groups[name]

        data = group("Sondajes")
        for k, n in [("collars", len(p.collars)), ("surveys", len(p.surveys)),
                     ("intervals", sum(len(v) for v in p.intervals.values())),
                     ("assays", sum(len(v) for v in (p.assays or {}).values()))]:
            data.addChild(QtWidgets.QTreeWidgetItem([f"{k}  ({n})"]))
        for key, (g, label, _b) in self.layer_defs.items():
            it = QtWidgets.QTreeWidgetItem([label])
            it.setData(0, QtCore.Qt.UserRole, key)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(0, QtCore.Qt.Checked if key in self.visible else QtCore.Qt.Unchecked)
            if key.startswith("solid:"):
                it.setIcon(0, self._swatch(scene.unit_color(p, key[6:])))
            elif key.startswith(("surface:", "points:")):
                it.setIcon(0, self._swatch(scene.unit_color(p, key.split(" ", 1)[1])))
            group(g).addChild(it)
        if p.vario is not None:
            group("Estimación").addChild(QtWidgets.QTreeWidgetItem([f"Variograma: {p.vario}"]))
        rep = group("Reportes")
        for u, v, t in p.volume_report():
            rep.addChild(QtWidgets.QTreeWidgetItem([f"{u}: {v / 1e6:,.2f} Mm³ · {t / 1e6:,.1f} Mt"]))
        self.tree.expandAll()
        self.tree.blockSignals(False)

    @staticmethod
    def _swatch(color):
        pm = QtGui.QPixmap(28, 28)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor(color))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(4, 4, 20, 20, 6, 6)
        p.end()
        pm.setDevicePixelRatio(2.0)
        return QtGui.QIcon(pm)

    # -- escena ---------------------------------------------------------------------
    def _kw(self, key):
        if key not in self.base_kw:
            self.base_kw[key] = self.layer_defs[key][2]()
        return dict(self.base_kw[key])

    def render_all(self):
        cam = self.plotter.camera_position if self.actors else None
        self.plotter.clear()
        self.actors.clear()
        for key in self.layer_defs:
            if key in self.visible:
                self._add(key)
        if self.clip:
            for u, face in scene.section_faces(self.project, *self.clip):
                if f"solid:{u}" in self.visible:
                    self.plotter.add_mesh(face, color=scene.unit_color(self.project, u), ambient=0.25, name=f"cut:{u}")
        self.plotter.set_scale(zscale=self.zscale.value())
        scene.decorate(self.plotter, self.project, self.zscale.value())
        self.plotter.add_camera_orientation_widget()
        if cam:
            self.plotter.camera_position = cam
        self._fill_shape_list()
        self.plotter.render()

    def _add(self, key):
        kw = self._kw(key)
        if self.clip and not key.startswith("topo"):
            kw = scene.section(kw, *self.clip)
        mesh = kw.pop("mesh")
        if mesh.n_points:
            self.actors[key] = self.plotter.add_mesh(mesh, name=key, **kw)
            if key in self.styles:
                self._apply_style(key, *self.styles[key])

    def _tree_toggled(self, item, _col):
        key = item.data(0, QtCore.Qt.UserRole)
        if not key:
            return
        if item.checkState(0) == QtCore.Qt.Checked:
            self.visible.add(key)
        else:
            self.visible.discard(key)
        self.render_all()
        self._show_props(key)

    def _fill_shape_list(self):
        self.shape_list.clear()
        for key, actor in self.actors.items():
            row = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(row)
            h.setContentsMargins(10, 3, 10, 3)
            h.setSpacing(12)
            eye = QtWidgets.QCheckBox()
            eye.setChecked(bool(actor.GetVisibility()))
            eye.toggled.connect(lambda c, a=actor: (a.SetVisibility(c), self.plotter.render()))
            h.addWidget(eye)
            lbl = QtWidgets.QLabel(self.layer_defs[key][1])
            lbl.setMinimumWidth(220)
            h.addWidget(lbl)
            c = actor.GetProperty().GetColor()
            btn = QtWidgets.QPushButton(objectName="Swatch")
            btn.setFixedSize(44, 18)
            cmap = self.base_kw.get(key, {}).get("cmap")
            if "scalars" in self.base_kw.get(key, {}):
                stops = ["#30123b", "#4686fb", "#1ae4b6", "#a2fc3c", "#fabb39", "#e4460a", "#7a0403"] \
                    if cmap == "turbo" else [scene.unit_color(self.project, u) for u in self.project.units]
                grad = ", ".join(f"stop:{i / (len(stops) - 1):.2f} {c_}" for i, c_ in enumerate(stops))
                btn.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {grad});")
                btn.setToolTip(cmap if isinstance(cmap, str) else "categórico")
            else:
                btn.setStyleSheet(f"background: rgb({int(c[0] * 255)},{int(c[1] * 255)},{int(c[2] * 255)});")
                btn.clicked.connect(lambda _=False, k=key, b=btn: self._pick_color(k, b))
            h.addWidget(btn)
            if actor.GetMapper().GetInput().GetNumberOfPolys():  # mallas (no puntos/líneas)
                st, sh = self.styles.get(key, ("Sólido", "Suave"))
                style = QtWidgets.QComboBox()
                style.addItems(STYLES)
                style.setCurrentText(st)
                shade = QtWidgets.QComboBox()
                shade.addItems(["Suave", "Plano"])
                shade.setCurrentText(sh)
                for w in (style, shade):
                    w.setFixedWidth(150 if w is style else 80)
                    w.currentTextChanged.connect(lambda _=None, k=key, a=style, b=shade: self._apply_style(k, a.currentText(), b.currentText()))
                    h.addWidget(w)
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal, minimum=0, maximum=100)
            s.setFixedWidth(160)
            s.setValue(int(actor.GetProperty().GetOpacity() * 100))
            s.valueChanged.connect(lambda v, a=actor: (a.GetProperty().SetOpacity(v / 100), self.plotter.render()))
            h.addWidget(s)
            h.addStretch()
            it = QtWidgets.QListWidgetItem()
            it.setSizeHint(row.sizeHint())
            self.shape_list.addItem(it)
            self.shape_list.setItemWidget(it, row)

    def _apply_style(self, key, style, shade):
        """Renderizado por capa (como Leapfrog): sólido, malla de alambre, sólido con aristas,
        puntos o transparente; sombreado suave o plano."""
        self.styles[key] = (style, shade)
        prop = self.actors[key].GetProperty()
        {"Malla (alambre)": prop.SetRepresentationToWireframe,
         "Puntos": prop.SetRepresentationToPoints}.get(style, prop.SetRepresentationToSurface)()
        prop.SetEdgeVisibility(style == "Sólido + aristas")
        prop.SetEdgeColor(0.05, 0.07, 0.09)
        prop.SetLineWidth(1.0)
        prop.SetPointSize(3.0)
        if style == "Translúcido":
            prop.SetOpacity(0.35)
        prop.SetInterpolationToFlat() if shade == "Plano" else prop.SetInterpolationToPhong()
        self.plotter.render()

    def _pick_color(self, key, btn):
        actor = self.actors[key]
        c = actor.GetProperty().GetColor()
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor(*[int(v * 255) for v in c]), self)
        if not col.isValid():
            return
        actor.GetProperty().SetColor(col.redF(), col.greenF(), col.blueF())
        self.base_kw[key]["color"] = col.name()
        if key.startswith("solid:"):
            self.project.cfg["colors"][key[6:]] = col.name()
        btn.setStyleSheet(f"background: {col.name()};")
        self._fill_tree()
        self.plotter.render()

    def _show_props(self, key):
        p = self.project
        self.prop_title.setText(self.layer_defs[key][1])
        info = ""

        def rows(pairs):
            return "<table cellspacing='0' cellpadding='3'>" + "".join(
                f"<tr><td style='color:{theme.TEXT2}'>{k}</td><td style='padding-left:14px'>{v}</td></tr>"
                for k, v in pairs) + "</table>"

        if key.startswith("solid:"):
            u = key[6:]
            v = p.model.volumes()[u]
            info = rows([("Volumen", f"{v / 1e6:,.2f} Mm³"), ("Densidad", f"{p.density(u)} t/m³"),
                         ("Tonelaje", f"{v * p.density(u) / 1e6:,.1f} Mt")])
        elif key == "blocks":
            g = p.blocks.cell_data["grade"]
            g = g[np.isfinite(g)]
            info = rows([("Bloques", f"{len(g):,}"), ("Tamaño", " × ".join(f"{b:g}" for b in p.cfg["block"]) + " m"),
                         ("Ley media", f"{g.mean():.3f} {p.cfg['unit']}"), ("Ley máx.", f"{g.max():.3f} {p.cfg['unit']}"),
                         ("Nugget", f"{p.vario.nugget:.4f}"), ("Alcance H/V", f"{p.vario.range_h:.0f} / {p.vario.range_v:.0f} m")])
        elif key.startswith("fault:"):
            f = p.cfg["faults"][int(key[6:])]
            info = rows([("Manteo", f"{f['dip']:.0f}°"), ("Dir. manteo", f"{f['dip_direction']:.0f}°"),
                         ("Punto", ", ".join(f"{c:.0f}" for c in f["point"]))])
        self.prop_info.setText(info)

    def _tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        key = item.data(0, QtCore.Qt.UserRole) if item else None
        if not key:
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction("Ver solo esto", lambda: self._solo(key))
        menu.addAction("Propiedades", lambda: self._show_props(key))
        if key.startswith(("solid:", "fault:", "topo", "surface:", "volume:")):
            menu.addAction("Exportar malla...", lambda: self._export_mesh(key))
        if key.startswith("volume:"):
            menu.addAction("Eliminar volumen", lambda: self._delete_volume(key[7:]))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _delete_volume(self, name):
        if QtWidgets.QMessageBox.question(self, "GeoForm", f"¿Eliminar el volumen «{name}»?") != QtWidgets.QMessageBox.Yes:
            return
        self.project.cfg["volumes"] = [v for v in self.project.cfg["volumes"] if v["name"] != name]
        self.rebuild()

    def _solo(self, key):
        self.visible = {key}
        self._fill_tree()
        self.render_all()

    def set_view(self, v):
        if self.project is None or not self.layer_defs:
            return
        scene.set_view(self.plotter, self.project, *v)
        self.plotter.render()
        self._update_cam_label()

    def _toggle_bg(self):
        scene.LIGHT = not scene.LIGHT
        self.base_kw.clear()  # las leyendas guardan el color de texto
        if self.layer_defs:
            self.render_all()

    def _set_zscale(self, z):
        self.zlabel.setText(f"Z ×{z:.1f}")
        if self.layer_defs:
            self.render_all()  # rehace la grilla de ejes con las cotas reales

    def _update_cam_label(self):
        d = np.array(self.plotter.camera.direction)
        plunge = np.degrees(np.arcsin(-d[2]))
        az = np.degrees(np.arctan2(d[0], d[1])) % 360
        self.cam_label.setText(f"Inclinación {plunge:+.0f}°   Azimut {az:.0f}°")

    def _apply_slicer(self):
        if not self.layer_defs:
            return
        if not self.slice_on.isChecked():
            self.clip = None
        else:
            b = np.array(self.plotter.bounds).reshape(3, 2)
            ax = [1, 0, 2][self.slice_dir.currentIndex()]
            o = np.zeros(3)
            o[ax] = b[ax, 0] + (b[ax, 1] - b[ax, 0]) * self.slice_pos.value() / 100
            n = np.zeros(3)  # se quita el lado de la cámara -> la cara de corte mira al usuario
            n[ax] = np.sign(self.plotter.camera.position[ax] - o[ax]) or 1.0
            if self.slice_flip.isChecked():
                n = -n
            self.clip = (tuple(n), tuple(o))
        self.render_all()

    # -- pestañas de análisis -------------------------------------------------------
    @staticmethod
    def _figure(w, h):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        theme.apply_mpl()
        fig = Figure(figsize=(w, h), layout="constrained")
        canvas = FigureCanvasQTAgg(fig)
        canvas.setStyleSheet(f"background: {theme.BG0};")
        return fig, canvas

    @staticmethod
    def _clear(lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                MainWindow._clear(it.layout())

    def _fill_variogram(self):
        from .estimation import spherical

        v, p = self.project.vario, self.project
        lay = self.vario_tab.layout()
        self._clear(lay)
        if v is None:
            lay.addWidget(QtWidgets.QLabel("Sin leyes o sin dominio de estimación definido.", objectName="Muted"))
            return
        kpis = QtWidgets.QHBoxLayout()
        kpis.setSpacing(12)
        for lab, val, sub in [("Modelo", "Esférico", f"{p.cfg['element']} en {p.cfg['domain']}"),
                              ("Nugget", f"{v.nugget:.3f}", f"{v.nugget / v.sill:.0%} del sill"),
                              ("Sill", f"{v.sill:.3f}", f"varianza {v.var:.3f}"),
                              ("Alcance horizontal", f"{v.range_h:.0f} m", "dirección horizontal"),
                              ("Alcance vertical", f"{v.range_v:.0f} m", f"anisotropía {v.range_v / v.range_h:.2f}")]:
            kpis.addWidget(card(lab, val, sub))
        lay.addLayout(kpis)
        fig, canvas = self._figure(10, 5.5)
        ax = fig.add_subplot(111)
        for (h, g, n), lab, col, r in [(v.horiz, "Horizontal", theme.SERIES[0], v.range_h),
                                       (v.vert, "Vertical", theme.SERIES[2], v.range_v),
                                       (v.omni, "Omnidireccional", theme.TEXT3, None)]:
            if not len(h):
                continue
            ax.scatter(h, g, s=16 + 90 * n / n.max(), color=col, alpha=0.85, edgecolors="none", label=f"{lab} · experimental", zorder=3)
            if r:
                hh = np.linspace(0, max(h.max(), r) * 1.1, 300)
                ax.plot(hh, spherical(hh, v.nugget, v.sill, r), color=col, label=f"{lab} · modelo ({r:.0f} m)", zorder=2)
                ax.axvline(r, color=col, lw=1, ls=(0, (2, 4)), alpha=0.6)
        ax.axhline(v.var, color=theme.TEXT2, lw=1, ls=(0, (1, 3)), label="Varianza")
        ax.set_xlabel("Distancia h (m)")
        ax.set_ylabel("γ(h)")
        ax.set_title("Semivariograma experimental y modelo ajustado")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.legend(loc="lower right", ncols=2)
        lay.addWidget(canvas, 1)

    def _fill_report(self):
        p = self.project
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(20, 16, 20, 20)
        lay.setSpacing(14)
        rep = p.volume_report()
        gt = p.grade_tonnage()
        kpis = QtWidgets.QHBoxLayout()
        kpis.setSpacing(12)
        kpis.addWidget(card("Sondajes", f"{len(p.collars)}",
                            f"{sum(len(v) for v in p.intervals.values()):,} intervalos litológicos"))
        kpis.addWidget(card("Volumen modelado", f"{sum(v for _, v, _ in rep) / 1e6:,.0f} Mm³", f"{len(p.units)} unidades"))
        val, _per = p.validation()
        kpis.addWidget(card("Validación", f"{val:.1%}", "metros de sondaje que coinciden con el modelo",
                            theme.ACCENT if val >= 0.9 else theme.AMBER))
        if gt:
            row = gt[min(3, len(gt) - 1)]
            el, un = p.cfg["element"], p.cfg["unit"]
            kpis.addWidget(card(f"Recurso > {row[0]:g}{un} {el}", f"{row[1] / 1e6:,.1f} Mt", f"dominio {p.cfg['domain']}", theme.ACCENT))
            kpis.addWidget(card("Ley media", f"{row[2]:.2f} {un}", f"{el} sobre la ley de corte", theme.AMBER))
            kpis.addWidget(card(f"{el} contenido", f"{row[3] / 1e3:,.0f} kt", "metal fino estimado"))
        if p.pit is not None:
            s = p.pit[1]
            kpis.addWidget(card("Pit óptimo", f"{s['t_mineral'] / 1e6:,.1f} Mt",
                                f"razón E/M {s['razon']:.1f} · US$ {s['valor'] / 1e6:,.0f} M", theme.SERIES[1]))
        lay.addLayout(kpis)

        fig, canvas = self._figure(11, 4.6)
        canvas.setMinimumHeight(380)
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.35])
        ax1 = fig.add_subplot(gs[0])
        names = [u for u, _, _ in rep][::-1]
        tons = [t / 1e6 for _, _, t in rep][::-1]
        bars = ax1.barh(names, tons, color=[scene.unit_color(p, u) for u in names], height=0.62)
        ax1.bar_label(bars, labels=[f"{t:,.0f} Mt" for t in tons], padding=6, color=theme.TEXT2, fontsize=9)
        ax1.set_title("Tonelaje por unidad")
        ax1.set_xlabel("Mt")
        ax1.grid(axis="y", visible=False)
        ax1.spines["left"].set_visible(False)
        ax1.set_xlim(0, max(tons) * 1.22)
        if gt:
            ax2 = fig.add_subplot(gs[1])
            c = [r[0] for r in gt]
            t = [r[1] / 1e6 for r in gt]
            ax2.fill_between(c, t, color=theme.SERIES[0], alpha=0.12)
            ax2.plot(c, t, "o-", color=theme.SERIES[0])
            ax2.set_xlabel(f"Ley de corte {p.cfg['element']} ({p.cfg['unit']})")
            ax2.set_ylabel("Toneladas (Mt)")
            ax3 = ax2.twinx()
            ax3.plot(c, [r[2] for r in gt], "s-", color=theme.SERIES[2])
            ax3.set_ylabel(f"Ley media ({p.cfg['unit']})")
            ax3.grid(False)
            ax3.spines["right"].set_visible(True)
            ax2.set_title(f"Curva ley-tonelaje · {p.cfg['domain']}")
            ax2.yaxis.label.set_color(theme.SERIES[0])  # el color del eje hace de leyenda
            ax3.yaxis.label.set_color(theme.SERIES[2])
        lay.addWidget(canvas)

        tables, cells = QtWidgets.QGridLayout(), []  # 2x2: cuatro tablas en fila quedaban truncadas
        def add(w, *_):
            tables.addWidget(w, len(cells) // 2, len(cells) % 2, QtCore.Qt.AlignTop)
            cells.append(w)
        tables.setSpacing(12)
        add(self._table("Unidades", ["Unidad", "Mm³", "t/m³", "Mt"],
                                     [(u, f"{v / 1e6:,.2f}", f"{p.density(u):.2f}", f"{t / 1e6:,.1f}") for u, v, t in rep],
                                     {u: scene.unit_color(p, u) for u, _, _ in rep}), 0, QtCore.Qt.AlignTop)
        if gt:
            add(self._table("Ley-tonelaje", ["Corte", "Mt", f"Ley {p.cfg['unit']}", f"{p.cfg['element']} kt"],
                                         [(f"{c_:.2f}", f"{t_ / 1e6:,.2f}", f"{g_:.3f}", f"{m_ / 1e3:,.1f}") for c_, t_, g_, m_ in gt]),
                             0, QtCore.Qt.AlignTop)
            add(self._table("Clasificación (corte 0)", ["Categoría", "Mt", f"Ley {p.cfg['unit']}", f"{p.cfg['element']} kt"],
                                         [(n, f"{t_ / 1e6:,.2f}", f"{g_:.3f}", f"{m_ / 1e3:,.1f}") for n, t_, g_, m_ in p.classification()],
                                         {"Medido": "#22c55e", "Indicado": "#f59e0b", "Inferido": "#ef4444"}), 0, QtCore.Qt.AlignTop)
        add(self._table("Validación por unidad", ["Unidad", "Acierto"],
                                     [(u, f"{v:.1%}") for u, v in _per.items()],
                                     {u: scene.unit_color(p, u) for u in _per}), 0, QtCore.Qt.AlignTop)
        lay.addLayout(tables)
        lay.addStretch()
        self.report_tab.setWidget(page)

    def _table(self, title, headers, rows, swatches=None):
        f = QtWidgets.QFrame(objectName="Card")
        v = QtWidgets.QVBoxLayout(f)
        v.setContentsMargins(4, 12, 4, 4)
        lab = QtWidgets.QLabel(title.upper(), objectName="KpiLabel")
        lab.setContentsMargins(12, 0, 0, 6)
        v.addWidget(lab)
        t = QtWidgets.QTableWidget(len(rows), len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().hide()
        t.setShowGrid(False)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        t.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        mono = QtGui.QFont("Cascadia Mono", 9)
        for i, r in enumerate(rows):
            for j, val in enumerate(r):
                it = QtWidgets.QTableWidgetItem(val)
                if j:
                    it.setFont(mono)
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                elif swatches:
                    it.setIcon(self._swatch(swatches[val]))
                t.setItem(i, j, it)
            t.setRowHeight(i, 30)
        t.setFixedHeight(40 + 30 * len(rows))
        v.addWidget(t)
        f.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        return f

    # -- acciones -------------------------------------------------------------------
    def new_project(self):
        d = NewProjectDialog(self)
        if d.exec():
            self.project = d.project()
            self.edit_parameters(load_first=True)

    def open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir proyecto", "", "GeoForm (*.geoform)")
        if path:
            self.project = Project.open(path)
            self.rebuild()

    def save_project(self):
        if self.project is None:
            return
        path = self.project.path
        if not path or not os.path.exists(os.path.dirname(path)):
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar proyecto", "proyecto.geoform", "GeoForm (*.geoform)")
        if path:
            self.log(f"Proyecto guardado: {self.project.save(path)}")

    def edit_parameters(self, load_first=False):
        if self.project is None:
            return
        try:
            if load_first or not hasattr(self.project, "units"):
                self.project.load()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "GeoForm", f"No se pudieron leer los datos: {e}")
            return
        d = ParametersDialog(self.project, self)
        if d.exec():
            d.apply()
            self.rebuild()

    def export(self):
        if self.project is None or self.project.model is None:
            return
        out = QtWidgets.QFileDialog.getExistingDirectory(self, "Carpeta de exportación")
        if out:
            from .export import export_all

            for f in export_all(self.project, out):
                self.log(f"Exportado: {f}")

    def _export_mesh(self, key):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar malla", key.replace(":", "_"),
                                                        "DXF (*.dxf);;OBJ (*.obj);;STL (*.stl);;VTK (*.vtk)")
        if path:
            from .export import write_dxf

            mesh = self._kw(key)["mesh"]
            if path.lower().endswith(".dxf"):
                write_dxf(mesh, path, key)
            else:
                mesh.extract_surface(algorithm="dataset_surface").save(path)
            self.log(f"Malla exportada: {path}")

    def screenshot(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar captura", "geoform.png", "PNG (*.png)")
        if path:
            self.plotter.screenshot(path)
            self.log(f"Captura guardada: {path}")


class NewProjectDialog(QtWidgets.QDialog):
    """Archivos de entrada de un proyecto nuevo."""
    FIELDS = [("collars", "Collars (CSV)*"), ("surveys", "Surveys (CSV)*"), ("intervals", "Litología (CSV)*"),
              ("assays", "Leyes (CSV)"), ("topography", "Topografía DEM (.asc)"), ("satellite", "Imagen (PNG/JPG)")]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Nuevo proyecto")
        self.resize(620, 0)
        f = QtWidgets.QFormLayout(self)
        f.setContentsMargins(20, 18, 20, 18)
        f.setVerticalSpacing(10)
        self.name = QtWidgets.QLineEdit("Proyecto")
        f.addRow("Nombre", self.name)
        self.edits = {}
        for key, label in self.FIELDS:
            e = QtWidgets.QLineEdit()
            b = QtWidgets.QPushButton("Buscar…")
            b.clicked.connect(lambda _=False, e=e: e.setText(QtWidgets.QFileDialog.getOpenFileName(self)[0] or e.text()))
            row = QtWidgets.QHBoxLayout()
            row.addWidget(e)
            row.addWidget(b)
            f.addRow(label, row)
            self.edits[key] = e
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        if all(self.edits[k].text() for k in ("collars", "surveys", "intervals")):
            self.accept()

    def project(self):
        return Project(None, name=self.name.text(), **{k: e.text() or None for k, e in self.edits.items()})


class ParametersDialog(QtWidgets.QDialog):
    """Orden estratigráfico, intrusivos, fallas, dominio de estimación y grillas."""

    def __init__(self, project, parent):
        super().__init__(parent)
        self.p = project
        self.setWindowTitle("Parámetros del modelo")
        self.resize(680, 920)
        f = QtWidgets.QFormLayout(self)
        f.setContentsMargins(20, 18, 20, 18)
        f.setVerticalSpacing(10)
        units = project.strat + [u for u in project.cfg["intrusions"] if u not in project.strat]
        self.order = QtWidgets.QListWidget()
        self.order.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        for u in units:
            it = QtWidgets.QListWidgetItem(u)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if u in project.cfg["intrusions"] else QtCore.Qt.Unchecked)
            self.order.addItem(it)
        f.addRow(QtWidgets.QLabel("UNIDADES · techo a base (arrastrar) · marcar = intrusivo", objectName="SectionTitle"))
        f.addRow(self.order)
        self.faults = QtWidgets.QTableWidget(0, 6)
        self.faults.setHorizontalHeaderLabels(["Nombre", "X", "Y", "Elev", "Dir. manteo", "Manteo"])
        self.faults.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for fl in project.cfg["faults"]:
            self._add_fault(fl)
        bf = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("+ Falla")
        add.clicked.connect(lambda: self._add_fault(None))
        rm = QtWidgets.QPushButton("− Falla")
        rm.clicked.connect(lambda: self.faults.removeRow(self.faults.currentRow()))
        bf.addWidget(add)
        bf.addWidget(rm)
        bf.addStretch()
        f.addRow(QtWidgets.QLabel("FALLAS · plano por punto + orientación", objectName="SectionTitle"))
        f.addRow(self.faults)
        f.addRow(bf)
        f.addRow(QtWidgets.QLabel("ESTIMACIÓN Y GRILLAS", objectName="SectionTitle"))
        self.domain = QtWidgets.QComboBox()
        self.domain.addItems(["(ninguno)"] + units)
        if project.cfg["domain"] in units:
            self.domain.setCurrentText(project.cfg["domain"])
        f.addRow("Dominio de estimación", self.domain)
        self.element = QtWidgets.QLineEdit(project.cfg["element"])
        f.addRow("Elemento", self.element)
        self.cell = QtWidgets.QDoubleSpinBox(minimum=2, maximum=100, value=project.cfg["cell"])
        f.addRow("Resolución del modelo (m)", self.cell)
        self.comp = QtWidgets.QDoubleSpinBox(minimum=1, maximum=50, value=project.cfg["composite"])
        f.addRow("Largo de compósito (m)", self.comp)
        self.block = QtWidgets.QDoubleSpinBox(minimum=2, maximum=100, value=project.cfg["block"][0])
        f.addRow("Tamaño de bloque (m)", self.block)
        self.veins = QtWidgets.QLineEdit(", ".join(project.cfg["veins"]))
        self.veins.setPlaceholderText("litologías separadas por coma, p. ej. Veta")
        f.addRow("Vetas", self.veins)
        from .pit import DEFAULTS as PIT
        f.addRow(QtWidgets.QLabel("PIT ÓPTIMO · parámetros económicos", objectName="SectionTitle"))
        self.pit = {}
        for key, label, lo, hi, dec in (("price", "Precio del metal (US$/t)", 0, 1e7, 0),
                                        ("recovery", "Recuperación (0-1)", 0, 1, 2),
                                        ("mine_cost", "Costo mina (US$/t)", 0, 1e3, 2),
                                        ("proc_cost", "Costo planta (US$/t)", 0, 1e3, 2),
                                        ("block", "Bloque del pit (m)", 5, 100, 0)):
            w = QtWidgets.QDoubleSpinBox(minimum=lo, maximum=hi, decimals=dec,
                                         value=float(project.cfg["pit"].get(key, PIT[key])))
            self.pit[key] = w
            f.addRow(label, w)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _add_fault(self, fl):
        if fl is None:
            c = np.array([v[:3] for v in self.p.collars.values()]).mean(axis=0)
            fl = {"name": f"Falla {self.faults.rowCount() + 1}", "point": [c[0], c[1], -c[2]], "dip_direction": 90, "dip": 70}
        r = self.faults.rowCount()
        self.faults.insertRow(r)
        for j, v in enumerate([fl["name"], *fl["point"], fl["dip_direction"], fl["dip"]]):
            self.faults.setItem(r, j, QtWidgets.QTableWidgetItem(f"{v:.1f}" if j else str(v)))

    def apply(self):
        c = self.p.cfg
        items = [self.order.item(i) for i in range(self.order.count())]
        c["intrusions"] = [it.text() for it in items if it.checkState() == QtCore.Qt.Checked]
        c["stratigraphy"] = [it.text() for it in items if it.checkState() != QtCore.Qt.Checked]
        c["faults"] = []
        for r in range(self.faults.rowCount()):
            v = [self.faults.item(r, j).text() for j in range(6)]
            c["faults"].append({"name": v[0], "point": [float(x) for x in v[1:4]],
                                "dip_direction": float(v[4]), "dip": float(v[5])})
        c["domain"] = None if self.domain.currentIndex() == 0 else self.domain.currentText()
        c["element"] = self.element.text()
        c["cell"], c["composite"] = self.cell.value(), self.comp.value()
        c["block"] = [self.block.value()] * 3
        c["veins"] = [v.strip() for v in self.veins.text().split(",") if v.strip()]
        c["pit"] = {k: w.value() for k, w in self.pit.items()}


def run(project, smoke=False):
    import sys

    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("GeoForm")
    theme.apply_qt(app)
    win = MainWindow(project)
    win.show()
    if smoke:  # test headless: espera el cálculo y sale
        loop = QtCore.QEventLoop()
        win._thread.done.connect(lambda *_: QtCore.QTimer.singleShot(500, loop.quit))
        loop.exec()
        return win
    sys.exit(app.exec())
