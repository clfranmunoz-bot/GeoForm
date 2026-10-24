"""Correlación de sondajes (estilo Leapfrog "Drillhole Correlation"): una columna por sondaje
con litología (bloques rotulados), ley en barras y curva, alineados por profundidad o por
cota del collar. Los sondajes se eligen de una lista; el orden de selección es el del panel.
"""
import numpy as np
from PySide6 import QtCore, QtWidgets

from . import scene, theme


def hole_logs(project, hid):
    """(litología [(from, to, lith)], leyes [(from, to, valor)], cota del collar)."""
    rows = (project.assays or {}).get(hid, [])
    return project.intervals.get(hid, []), rows, project.collars[hid][2] * -1  # collar z motor -> elevación


def draw_correlation(fig, project, holes, by_elevation=False, max_depth=None):
    """Dibuja el panel en `fig` (matplotlib). Devuelve los ejes por sondaje."""
    from matplotlib.ticker import MultipleLocator

    fig.clear()
    if not holes:
        return []
    el = f"{project.cfg['element']} ({project.cfg['unit']})"
    from matplotlib import colormaps

    vmax = scene.grade_clim(project)[1] if project.assays else 1.0  # escala común a todo el proyecto
    cmap = colormaps[scene.GRADE_CMAP]
    axes = fig.subplots(1, len(holes), sharey=True, squeeze=False)[0]
    for ax, hid in zip(axes, holes):
        lith, assays, z0 = hole_logs(project, hid)
        sgn, off = (-1, z0) if by_elevation else (1, 0.0)  # eje y: profundidad o cota
        y = lambda d: off + sgn * d  # noqa: E731
        for f, t, l in lith:  # columna litológica (0..1 del eje x)
            c = scene.unit_color(project, l) if l in project.units else "#9ca3af"
            ax.fill_between([0, 0.32], y(f), y(t), color=c, lw=0)
            ax.plot([0, 0.32], [y(f)] * 2, color="#0d1117", lw=0.6)
            if t - f >= 6:
                ax.text(0.16, y((f + t) / 2), f"{l}\n{t - f:.1f}", ha="center", va="center", fontsize=7,
                        color="#0d1117")
        if assays:
            a = np.array(assays, float)
            w = 0.3 * np.clip(a[:, 2] / vmax, 0, 1)  # barras de ley (0.36..0.66)
            for (f, t, g), wi in zip(a, w):
                ax.fill_between([0.36, 0.36 + max(wi, 0.004)], y(f), y(t), color=cmap(min(g / vmax, 1.0)), lw=0)
            mid = (a[:, 0] + a[:, 1]) / 2  # curva suavizada (0.70..1)
            ax.plot(0.70 + 0.3 * np.clip(np.convolve(a[:, 2], np.ones(3) / 3, "same") / vmax, 0, 1), y(mid),
                    color=theme.SERIES[1], lw=1.0)
        ax.set_xlim(0, 1)
        ax.set_xticks([0.16, 0.51, 0.85], ["Litología", el, "Curva"], fontsize=7)
        ax.tick_params(axis="x", length=0)
        ax.set_title(hid, loc="left", fontsize=10, fontweight="bold")
        ax.grid(axis="x", visible=False)
        ax.yaxis.set_minor_locator(MultipleLocator(5))
    a0 = axes[0]
    a0.set_ylabel("Elevación (m)" if by_elevation else "Profundidad (m)")
    if not by_elevation:
        a0.invert_yaxis()
        if max_depth:
            a0.set_ylim(max_depth, 0)
    return list(axes)


class CorrelationView(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(12, 8, 12, 8)
        side = QtWidgets.QVBoxLayout()
        side.addWidget(QtWidgets.QLabel("SONDAJES", objectName="SectionTitle"))
        self.search = QtWidgets.QLineEdit(placeholderText="Filtrar…")
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list.setFixedWidth(170)
        self.align = QtWidgets.QComboBox()
        self.align.addItems(["Alinear por profundidad", "Alinear por cota (collar)"])
        self.depth = QtWidgets.QSpinBox(minimum=0, maximum=5000, value=0, suffix=" m", specialValueText="Prof. completa")
        for w in (self.search, self.list, self.align, self.depth):
            side.addWidget(w)
        side.addWidget(QtWidgets.QLabel("Ctrl/Shift + clic para varios (máx. 8)", objectName="Muted"))
        h.addLayout(side)
        self.fig, self.canvas = self.win._figure(12, 7)
        h.addWidget(self.canvas, 1)
        self.search.textChanged.connect(self._filter)
        self.list.itemSelectionChanged.connect(self.draw)
        self.align.currentIndexChanged.connect(self.draw)
        self.depth.valueChanged.connect(self.draw)

    def refresh(self):
        p = self.win.project
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems(sorted(p.intervals))
        best = sorted(p.intervals, key=lambda h: -np.mean([r[2] for r in (p.assays or {}).get(h, [])] or [0]))[:5]
        for i in range(self.list.count()):  # vista inicial: los 5 sondajes de mayor ley media
            self.list.item(i).setSelected(self.list.item(i).text() in best)
        self.list.blockSignals(False)
        self.draw()

    def _filter(self, text):
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(text.lower() not in it.text().lower())

    def draw(self):
        p = self.win.project
        if p is None:
            return
        holes = [it.text() for it in self.list.selectedItems()][:8]
        draw_correlation(self.fig, p, holes, self.align.currentIndex() == 1, self.depth.value() or None)
        self.canvas.draw_idle()
