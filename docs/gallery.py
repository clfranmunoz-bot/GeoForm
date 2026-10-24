"""Galería de capturas del proyecto demo -> docs/img/*.png  (python docs/gallery.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geoform.project import demo_project  # noqa: E402
from geoform.scene import plot_project  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
os.makedirs(OUT, exist_ok=True)
p = demo_project().load().build()
solids = {f"solid:{u}" for u in p.units}
cy = sum(c[1] for c in p.collars.values()) / len(p.collars)
shots = {
    "1_modelo_geologico": dict(keys=solids | {"fault:0", "topo:contours"}, view=(200, 28)),
    "2_corte_falla_porfido": dict(keys=solids | {"fault:0", "holes:lith"}, clip=((0, 1, 0), (0, cy, 0)), view=(20, 22)),
    "3_topografia_satelite": dict(keys={"topo", "topo:contours", "holes:lith"}, view=(215, 35)),
    "4_topografia_elevacion": dict(keys={"topo:elev", "topo:contours"}, view=(160, 35), zscale=2.5),
    "5_leyes_kriging": dict(keys={"holes:grade", "blocks", "solid:Porfido"}, opacity={"solid:Porfido": 0.25}, view=(250, 20, 1.4)),
}
for name, kw in shots.items():
    print(plot_project(p, screenshot=os.path.join(OUT, name + ".png"), **kw))
with open(os.path.join(OUT, "reporte.txt"), "w", encoding="utf-8") as fh:
    fh.write(p.report())
