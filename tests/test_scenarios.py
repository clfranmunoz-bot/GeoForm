"""Batería de escenarios de modelamiento sobre el yacimiento sintético (verdad conocida).

python -m tests.test_scenarios   -> tabla: escenario, tiempo, acierto litológico, error.
Cada escenario cambia datos o parámetros (sin topografía, sin falla, malla rala, dos fallas,
celda fina...) y mide contra synth.lithology.
"""
import os
import tempfile
import time

import numpy as np

from geoform import synth
from geoform.project import Project

FAULT2 = {"name": "Falla N", "point": [1250.0, 2450.0, 400.0], "dip_direction": 200.0, "dip": 80.0}


def accuracy(p, n=3000):
    rng = np.random.default_rng(3)
    q = np.column_stack([rng.uniform(1050, 1550, n), rng.uniform(2050, 2550, n), rng.uniform(100, 520, n)])
    truth = np.array([synth.lithology(*r) if r[2] < synth.topo_elev(r[0], r[1]) else None for r in q])
    ok = truth != None  # noqa: E711
    pred = np.array(p.units + ["aire"])[p.model.label_at(q[ok] * [1, 1, -1])]
    return float((pred == truth[ok]).mean())


def scenarios(base):
    std = dict(assays="assays.csv", topography="terrain.asc", stratigraphy=synth.STRAT,
               intrusions=[synth.INTRUSION], veins=[synth.VEIN], faults=[synth.FAULT], domain=synth.INTRUSION)
    yield "base (celda 10)", base, std
    yield "sin topografía (DEM)", base, {**std, "topography": None}
    yield "sin falla declarada", base, {**std, "faults": []}
    yield "dos fallas (una ficticia)", base, {**std, "faults": [synth.FAULT, FAULT2]}
    yield "estratigrafía automática", base, {**std, "stratigraphy": None}
    yield "celda fina (6 m)", base, {**std, "cell": 6.0}
    yield "trazos a mano + volumen", base, {**std, "picks": {"Sedimentario": [[1300, 2300, 330.0]]},
                                            "volumes": [{"name": "Paquete", "top": "Techo Volcanico",
                                                         "bottom": "Techo Basamento"}]}
    sparse = os.path.join(os.path.dirname(base), "sparse")
    synth.generate(sparse, spacing=120.0)
    yield "malla rala (120 m)", sparse, std


def main():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "base")
        synth.generate(base)
        for name, folder, cfg in scenarios(base):
            p = Project(os.path.join(folder, "x.geoform"), **cfg)
            p.log = lambda *_: None
            t = time.time()
            try:
                p.load().build()
                acc = accuracy(p)
                gt = p.grade_tonnage()
                rows.append((name, time.time() - t, acc, f"{gt[0][1] / 1e6:.1f} Mt" if gt else "-", ""))
            except Exception as e:  # el informe debe listar todos los escenarios
                rows.append((name, time.time() - t, float("nan"), "-", f"{type(e).__name__}: {e}"))
    print(f"{'Escenario':<28}{'s':>6}{'acierto':>9}{'recurso':>10}  error")
    for n, s, a, r, e in rows:
        print(f"{n:<28}{s:>6.1f}{a:>9.1%}{r:>10}  {e}")
    assert all(not e for *_, e in rows), "hay escenarios con error"
    assert all(a > 0.85 for _, _, a, _, e in rows if not e), "acierto bajo"


if __name__ == "__main__":
    main()
