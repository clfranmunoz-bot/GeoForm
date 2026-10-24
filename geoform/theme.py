"""Sistema de diseño de GeoForm: tokens de color, tipografía, iconos SVG (estilo
Lucide), hoja de estilos Qt y estilo de matplotlib. Una sola fuente de verdad
para la GUI, los gráficos y la escena 3D."""
import os as _os

# -- tokens ---------------------------------------------------------------------------
BG0 = "#0d1117"      # fondo de la app
BG1 = "#151b23"      # paneles
BG2 = "#1c2430"      # inputs, tarjetas
BG3 = "#253041"      # hover
BORDER = "#2a3441"
TEXT = "#e6edf3"
TEXT2 = "#8b98a8"
TEXT3 = "#5c6878"
ACCENT = "#2dd4bf"   # teal
ACCENT_D = "#14b8a6"
AMBER = "#fbbf24"
RED = "#f87171"
SERIES = ["#2dd4bf", "#60a5fa", "#fbbf24", "#f472b6", "#a78bfa", "#fb923c", "#4ade80"]

SANS = '"Inter", "Segoe UI Variable Text", "SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif'
MONO = '"JetBrains Mono", "Cascadia Mono", "SF Mono", "Consolas", monospace'
SANS_LIST = ["Inter", "Segoe UI Variable Text", "SF Pro Text", "Helvetica Neue", "Segoe UI", "DejaVu Sans"]

# 3D (VTK solo trae arial/courier/times)
SCENE_BG = ("#0d1117", "#243142")  # abajo, arriba
SCENE_TEXT = "#c9d4e0"
SCENE_GRID = "#7d8da1"

CHECK = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "check.svg").replace("\\", "/")

# -- iconos (paths Lucide, 24x24, trazo) ---------------------------------------------------
ICONS = {
    "new": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M12 18v-6M9 15h6"/>',
    "open": '<path d="M6 14l1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    "params": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "run": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "export": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "camera": '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    "iso": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.27 6.96L12 12.01l8.73-5.05M12 22.08V12"/>',
    "plan": '<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4zM8 2v16M16 6v16"/>',
    "north": '<circle cx="12" cy="12" r="10"/><path d="M12 6l3 10-3-2-3 2z"/>',
    "east": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "slice": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.12 15.88M14.47 14.48L20 20M8.12 8.12L12 12"/>',
    "layers": '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>',
    "section": '<path d="M3 3v18h18"/><path d="M3 15c4-1 6-5 10-5s5 3 8 2"/><path d="M3 9c5 0 7-3 11-3"/>',
    "pen": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "drill": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "topo": '<path d="M8 3l4 8 5-5 5 15H2L8 3z"/>',
    "fault": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
    "blocks": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    "vario": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "report": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "scene": '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 7v10l10 5 10-5V7"/>',
    "logo": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/><path d="M7.5 9.5l9-5"/>',
}

GROUP_ICON = {"Sondajes": "drill", "Topografía": "topo", "Modelos geológicos": "iso",
              "Estructural": "fault", "Compósitos": "target", "Modelos de bloques": "blocks",
              "Estimación": "vario", "Reportes": "report",
              "Superficies": "section", "Volúmenes del usuario": "layers"}


def icon(name, color=TEXT2, size=20):
    """QIcon desde un path Lucide (SVG renderizado a la resolución pedida)."""
    from PySide6 import QtCore, QtGui, QtSvg

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    r = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(2.0)
    return QtGui.QIcon(pm)


# -- Qt -------------------------------------------------------------------------------
QSS = f"""
* {{ font-family: {SANS}; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG0}; }}
QToolBar#Header {{ background: {BG1}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px 4px; spacing: 2px; }}
QLabel#Brand {{ font-size: 13pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#ProjectChip {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 11px; padding: 2px 10px; color: {TEXT2}; font-size: 9pt; }}
QLabel#Muted, QLabel#SectionTitle {{ color: {TEXT2}; }}
QLabel#SectionTitle {{ font-size: 8pt; font-weight: 600; letter-spacing: 1.2px; padding-top: 10px; }}
QLabel#PropTitle {{ font-size: 12pt; font-weight: 600; }}

QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 5px 9px; color: {TEXT}; }}
QToolButton:hover {{ background: {BG3}; }}
QToolButton:pressed, QToolButton:checked {{ background: {BG2}; border-color: {BORDER}; }}
QToolButton#Primary {{ background: {ACCENT_D}; color: #04201c; font-weight: 600; }}
QToolButton#Primary:hover {{ background: {ACCENT}; }}
QToolButton#Seg {{ border-radius: 0; padding: 5px 10px; color: {TEXT2}; }}
QToolButton#Seg:hover {{ color: {TEXT}; }}
QFrame#SegGroup {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px; }}

QDockWidget::title {{ background: {BG1}; color: {TEXT2}; padding: 9px 12px; text-transform: uppercase;
                     font-size: 8pt; font-weight: 600; letter-spacing: 1.2px; border-bottom: 1px solid {BORDER}; }}
QDockWidget > QWidget {{ background: {BG1}; }}
QMainWindow > QTabBar {{ background: {BG1}; }}
QMainWindow > QTabBar::tab {{ background: {BG1}; color: {TEXT2}; padding: 7px 16px; min-width: 70px; border: none;
                            border-top: 2px solid transparent; font-size: 9pt; }}
QMainWindow > QTabBar::tab:selected {{ color: {TEXT}; border-top: 2px solid {ACCENT}; }}
QMainWindow::separator {{ background: {BG0}; width: 4px; height: 4px; }}
QMainWindow::separator:hover {{ background: {ACCENT_D}; }}

QTreeWidget, QListWidget, QTableWidget, QPlainTextEdit {{ background: {BG1}; border: none; outline: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 4px 2px; border-radius: 6px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {BG2}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {BG3}; color: {TEXT}; }}
QTreeWidget::branch {{ background: transparent; }}
QPlainTextEdit#Console {{ font-family: {MONO}; font-size: 9pt; color: {TEXT2}; padding: 6px; }}

QTabWidget::pane {{ border: none; background: {BG0}; }}
QTabBar {{ background: {BG0}; }}
QTabBar::tab {{ background: transparent; color: {TEXT2}; padding: 9px 18px; margin: 6px 2px 0 2px;
                border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

QPushButton {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 7px; padding: 6px 14px; }}
QPushButton:hover {{ background: {BG3}; border-color: {TEXT3}; }}
QPushButton#Swatch {{ border-radius: 6px; padding: 0; border: 1px solid rgba(255,255,255,0.15); }}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 7px;
    padding: 5px 8px; selection-background-color: {ACCENT_D}; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT_D}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {BG2}; border: 1px solid {BORDER}; selection-background-color: {BG3}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator, QTreeWidget::indicator, QListWidget::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid {TEXT3}; background: {BG2}; }}
QCheckBox::indicator:checked, QTreeWidget::indicator:checked, QListWidget::indicator:checked {{ background: {ACCENT_D}; border-color: {ACCENT_D};
    image: url({CHECK}); }}

QSlider::groove:horizontal {{ height: 4px; background: {BG3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT_D}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BG3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BG3}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}

QHeaderView::section {{ background: {BG1}; color: {TEXT2}; border: none; border-bottom: 1px solid {BORDER};
                        padding: 7px 10px; font-size: 8pt; font-weight: 600; letter-spacing: 0.8px; }}
QTableWidget {{ gridline-color: {BORDER}; }}
QTableWidget::item {{ padding: 4px 10px; border-bottom: 1px solid {BORDER}; }}

QFrame#Card {{ background: {BG1}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#KpiValue {{ font-size: 20pt; font-weight: 600; }}
QLabel#KpiLabel {{ color: {TEXT2}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#KpiSub {{ color: {TEXT3}; font-size: 9pt; }}

QWidget#Overlay {{ background: rgba(13,17,23,0.82); }}
QLabel#OverlayTitle {{ font-size: 14pt; font-weight: 600; }}
QProgressBar {{ background: {BG2}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QStatusBar {{ background: {BG1}; border-top: 1px solid {BORDER}; color: {TEXT2}; }}
QStatusBar QLabel {{ color: {TEXT2}; padding: 0 10px; font-size: 9pt; }}
QMenu {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {BG3}; }}
QToolTip {{ background: {BG2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 8px; border-radius: 6px; }}
QMessageBox {{ background: {BG1}; }}
"""


def apply_qt(app):
    from PySide6 import QtGui

    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    for role, col in [(QtGui.QPalette.Window, BG0), (QtGui.QPalette.Base, BG1), (QtGui.QPalette.AlternateBase, BG2),
                      (QtGui.QPalette.Text, TEXT), (QtGui.QPalette.WindowText, TEXT), (QtGui.QPalette.Button, BG2),
                      (QtGui.QPalette.ButtonText, TEXT), (QtGui.QPalette.Highlight, ACCENT_D),
                      (QtGui.QPalette.HighlightedText, "#04201c"), (QtGui.QPalette.ToolTipBase, BG2),
                      (QtGui.QPalette.ToolTipText, TEXT), (QtGui.QPalette.PlaceholderText, TEXT3)]:
        pal.setColor(role, QtGui.QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    for fam in ("Inter", "Segoe UI Variable Text", "SF Pro Text", "Segoe UI"):
        if fam in QtGui.QFontDatabase.families():
            f = QtGui.QFont(fam, 10)
            f.setHintingPreference(QtGui.QFont.PreferNoHinting)
            app.setFont(f)
            break


# -- matplotlib ------------------------------------------------------------------------
def apply_mpl():
    import matplotlib
    from cycler import cycler

    matplotlib.rcParams.update({
        "figure.facecolor": BG0, "axes.facecolor": BG1, "savefig.facecolor": BG0,
        "axes.edgecolor": BORDER, "axes.labelcolor": TEXT2, "axes.titlecolor": TEXT,
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.titlepad": 14,
        "axes.labelsize": 10, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": BORDER, "grid.linewidth": 0.8, "grid.alpha": 1.0,
        "axes.prop_cycle": cycler(color=SERIES),
        "xtick.color": TEXT3, "ytick.color": TEXT3, "xtick.labelcolor": TEXT2, "ytick.labelcolor": TEXT2,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 6, "ytick.major.pad": 6,
        "legend.frameon": False, "legend.labelcolor": TEXT2, "legend.fontsize": 9,
        "font.family": "sans-serif", "font.sans-serif": SANS_LIST, "font.size": 10, "text.color": TEXT,
        "lines.linewidth": 2.2, "lines.markersize": 6,
    })
