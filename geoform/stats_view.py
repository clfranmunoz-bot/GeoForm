"""Pestaña Estadística: histograma de compósitos con percentiles y top-cut (capping), y swath
plots (validación del kriging: media de compósitos vs. media de bloques por franjas X, Y, Z)."""
import numpy as np
from PySide6 import QtWidgets

from . import theme
from .estimation import stats, swath


class StatsView(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(20, 12, 20, 12)
        bar = QtWidgets.QHBoxLayout()
        self.info = QtWidgets.QLabel("", objectName="Muted")
        self.topcut = QtWidgets.QDoubleSpinBox(minimum=0, maximum=1e6, decimals=3, specialValueText="sin top-cut")
        self.topcut.setToolTip("Ley máxima de los compósitos antes del variograma y el kriging")
        apply = QtWidgets.QPushButton("Aplicar top-cut y recalcular", objectName="Primary")
        apply.clicked.connect(self._apply)
        bar.addWidget(self.info, 1)
        bar.addWidget(QtWidgets.QLabel("Top-cut"))
        bar.addWidget(self.topcut)
        bar.addWidget(apply)
        v.addLayout(bar)
        self.fig, self.canvas = self.win._figure(12, 7)
        v.addWidget(self.canvas, 1)

    def refresh(self):
        p = self.win.project
        self.fig.clear()
        raw = getattr(p, "comp_raw", None)
        if raw is None or p.comp is None:
            self.info.setText("Sin compósitos de ley en el dominio.")
            self.canvas.draw_idle()
            return
        s = stats(raw)
        el = f"{p.cfg['element']} ({p.cfg['unit']})"
        self.topcut.setValue(p.cfg["topcut"] or 0)
        self.info.setText("   ·   ".join(f"{k} {v:,.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in s.items()))
        gs = self.fig.add_gridspec(2, 3, height_ratios=[1.1, 1])
        ax = self.fig.add_subplot(gs[0, :])
        ax.hist(raw, bins=50, color=theme.SERIES[0], alpha=0.8)
        for k, c in (("P95", theme.SERIES[2]), ("P99", theme.SERIES[3])):
            ax.axvline(s[k], color=c, ls="--", lw=1.2, label=f"{k} = {s[k]:.3f}")
        if p.cfg["topcut"]:
            ax.axvline(p.cfg["topcut"], color=theme.RED, lw=2, label=f"Top-cut = {p.cfg['topcut']:g}")
        ax.set_title(f"Histograma de compósitos {p.cfg['composite']:g} m · dominio {p.cfg['domain']}", loc="left")
        ax.set_xlabel(el)
        ax.set_ylabel("Frecuencia")
        ax.legend(loc="upper right")
        if p.blocks is not None:
            for i, (name, w) in enumerate((("Este X", 25), ("Norte Y", 25), ("Elevación Z", 20))):
                a = self.fig.add_subplot(gs[1, i])
                c, mc, mb, n = swath(*p.comp, p.blocks, i, w)
                a.bar(c, n / max(n.max(), 1) * np.nanmax(mc) * 0.4, width=w * 0.8, color=theme.TEXT3, alpha=0.35,
                      label="nº compósitos")
                a.plot(c, mc, "o-", color=theme.SERIES[0], ms=3, label="Compósitos")
                a.plot(c, mb, "s-", color=theme.SERIES[2], ms=3, label="Bloques (kriging)")
                a.set_title(f"Swath {name}", loc="left")
                a.set_xlabel(f"{name} (m)")
                if i == 0:
                    a.set_ylabel(el)
                    a.legend(fontsize=7)
        self.canvas.draw_idle()

    def _apply(self):
        p = self.win.project
        p.cfg["topcut"] = self.topcut.value() or None
        self.win.rebuild()
