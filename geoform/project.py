"""Proyecto GeoForm (.geoform, JSON): rutas de datos + parámetros del modelo.

Rutas relativas al archivo del proyecto. build() corre todo el pipeline:
datos -> modelo geológico -> compósitos -> variograma -> block model -> reportes.
"""
import json
import os

import numpy as np

from .app import DATA_DIR, load_assays, load_project

DEFAULTS = {
    "name": "Proyecto",
    "collars": "collars.csv", "surveys": "surveys.csv", "intervals": "intervals.csv",
    "assays": None, "topography": None, "satellite": None,
    "stratigraphy": None,          # techo -> base; None = orden por profundidad media
    "intrusions": [],
    "veins": [],                   # litologías modeladas como veta (techo/piso sobre plano medio)
    "faults": [],                  # [{name, point [x,y,elev], dip_direction, dip}]
    "cell": 10.0,
    "element": "Cu", "unit": "%",
    "domain": None,                # litología donde se estima la ley
    "composite": 10.0,
    "block": [10.0, 10.0, 10.0],
    "density": {},                 # {litología: t/m3}; default 2.6
    "cutoffs": [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5],
    "colors": {},
    "picks": {},                   # {unidad: [[x,y,elev]]} contactos trazados en el perfil 2D
    "volumes": [],                 # [{name, top, bottom}] volúmenes entre superficies
    "topcut": None,                # ley máxima de compósitos (capping); None = sin recorte
    "shells": [0.5, 1.0],          # leyes de corte de las envolventes de ley (modelo numérico)
    "pit": {},                     # parámetros económicos del pit (ver pit.DEFAULTS)
    "drift": "linear",             # tendencia de los RBF del modelo geológico: linear | quadratic
    "anisotropy": {"bearing": 0.0, "plunge": 0.0, "ratios": [1.0, 1.0, 1.0]},  # elipsoide de los RBF
    "method": "kriging",           # estimación de bloques: kriging | idw | nearest
    "simulations": 0,              # realizaciones SGS (0 = no simular); ~3 s c/u en el demo
    "smu": [1, 1, 1],              # re-bloqueo a SMU en bloques (fx, fy, fz) para la curva ley-tonelaje
    "mesh_refinement": 1,          # 1=sin subdividir (rápido), 2=Loop, 3=Butterfly (suaviza contactos voxel)
}
FILE_KEYS = ("collars", "surveys", "intervals", "assays", "topography", "satellite")


class Project:
    def __init__(self, path=None, **cfg):
        self.path = path
        self.cfg = {**DEFAULTS, **cfg}
        self.model = self.blocks = self.vario = None
        self.pit = self.xval = self.sims = None
        self.comp = self.all_comp = None
        self.log = print

    # -- E/S ------------------------------------------------------------------------
    @classmethod
    def open(cls, path):
        with open(path, encoding="utf-8") as fh:
            return cls(os.path.abspath(path), **json.load(fh))

    def save(self, path=None):
        new = os.path.abspath(path or self.path)
        if self.path and os.path.dirname(new) != os.path.dirname(self.path):
            for k in FILE_KEYS:
                if self.cfg.get(k):  # rutas relativas -> absolutas al mover el proyecto
                    self.cfg[k] = self.file(k)
        self.path = new
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.cfg, fh, indent=2, ensure_ascii=False)
        return self.path

    def file(self, key):
        p = self.cfg.get(key)
        if not p:
            return None
        return p if os.path.isabs(p) else os.path.join(os.path.dirname(self.path or DATA_DIR + os.sep), p)

    # -- pipeline -------------------------------------------------------------------
    def load(self):
        self.collars, self.surveys, self.intervals, units = load_project(
            self.file("collars"), self.file("surveys"), self.file("intervals"))
        intr, veins = self.cfg["intrusions"], self.cfg["veins"]
        self.strat = [u for u in (self.cfg["stratigraphy"] or units) if u not in intr and u not in veins]
        self.units = self.strat + list(intr) + [v for v in veins if v in units]
        self.assays = load_assays(self.file("assays"), self.cfg["element"]) if self.file("assays") else None
        self.dem = None
        if self.file("topography"):
            from .topography import load_dem
            self.dem = load_dem(self.file("topography"))
        return self

    def build(self, estimate=True):
        from .geomodel import GeoModel

        self.log(f"Modelo geológico: {len(self.collars)} sondajes, unidades {', '.join(self.units)}")
        self.model = GeoModel(self.collars, self.surveys, self.intervals, self.strat,
                              self.cfg["intrusions"], self.cfg["faults"], self.dem, self.cfg["cell"],
                              self.cfg["picks"], self.cfg["volumes"], self.units[len(self.strat) + len(self.cfg["intrusions"]):],
                              mesh_refinement=self.cfg["mesh_refinement"], drift=self.cfg["drift"],
                              anisotropy=self.cfg["anisotropy"]).build()
        self.blocks = self.vario = self.comp = self.all_comp = self.pit = self.xval = self.sims = None
        if estimate and self.assays:
            self.estimate()
        return self

    def estimate(self):
        from .estimation import Variogram, domain_block_model, domain_composites

        dom = self.cfg["domain"]
        xyz, vals, _ = domain_composites(self.collars, self.surveys, self.intervals, self.assays,
                                         dom, self.cfg["composite"])
        if len(vals) < 10:
            self.log(f"Estimación omitida: solo {len(vals)} compósitos en {dom or 'todo'}")
            return None
        self.comp_raw = vals
        if self.cfg["topcut"]:
            n = int((vals > self.cfg["topcut"]).sum())
            vals = np.minimum(vals, self.cfg["topcut"])
            self.log(f"Top-cut {self.cfg['topcut']}: {n} compósitos recortados")
        self.comp = (xyz, vals)
        self.all_comp = domain_composites(self.collars, self.surveys, self.intervals, self.assays,
                                          None, self.cfg["composite"])[:2]
        self.vario = Variogram(xyz, vals)
        self.log(f"Variograma ({len(vals)} compósitos en {dom or 'todo'}): {self.vario}")
        if dom:
            from .estimation import cross_validate
            from .pit import optimize

            self.blocks = domain_block_model(self.model, dom, xyz, vals, tuple(self.cfg["block"]), self.vario, self.cfg["method"])
            self.xval = cross_validate(xyz, vals, self.vario)
            self.log("Validación cruzada: " + ", ".join(f"{k} {v:.3f}" for k, v in self.xval[2].items()))
            if self.cfg["simulations"]:
                self.simulate()
            self.pit = optimize(self, self.cfg["pit"])
            s = self.pit[1]
            self.log(f"Pit óptimo: {s['t_mineral'] / 1e6:.1f} Mt mineral a {s['ley']:.2f}, razón E/M {s['razon']:.2f}")
        return self.blocks

    def simulate(self):
        """SGS en los bloques del dominio: cell_data 'prob' = P(ley ≥ primera envolvente) y
        self.sims = (corte, toneladas por realización sobre el corte)."""
        from .estimation import sgs

        b, n = self.blocks, self.cfg["simulations"]
        m = b.cell_data["domain"] > 0
        self.log(f"SGS: {n} realizaciones en {int(m.sum()):,} bloques")
        s = sgs(*self.comp, np.asarray(b.cell_centers().points)[m], self.vario, n_real=n)
        c = self.cfg["shells"][0]
        prob = np.full(b.n_cells, np.nan)
        prob[m] = (s >= c).mean(axis=1)
        b.cell_data["prob"] = prob
        bt = float(np.prod(self.cfg["block"])) * self.density(self.cfg["domain"])
        self.sims = (c, (s >= c).sum(axis=0) * bt)
        self.log("SGS t ≥ {:g}: P10 {:,.0f} · P50 {:,.0f} · P90 {:,.0f}".format(c, *self.sim_percentiles()))

    def sim_percentiles(self):
        return np.percentile(self.sims[1], [10, 50, 90])

    # -- reportes -------------------------------------------------------------------
    def density(self, unit):
        return float(self.cfg["density"].get(unit, 2.6))

    def volume_report(self):
        """[(unidad, m3, t)]"""
        out = [(u, v, v * self.density(u)) for u, v in self.model.volumes().items()]
        return out + [(n, self.model.custom_volume(n), self.model.custom_volume(n) * self.density(n)) for n in self.model.custom]

    def grade_tonnage(self):
        """Curva ley-tonelaje; con smu != [1,1,1] sobre bloques SMU diluidos (re-bloqueo)."""
        from .estimation import grade_tonnage, regularize

        if self.blocks is None:
            return []
        g, f = self.blocks.cell_data["grade"], self.cfg["smu"]
        if f != [1, 1, 1]:
            g, inside = regularize(g, np.array(self.blocks.dimensions) - 1, f)
            g[inside == 0] = np.nan
        bv = float(np.prod(self.cfg["block"])) * np.prod(f)
        return grade_tonnage(g, bv, self.density(self.cfg["domain"]), self.cfg["cutoffs"])

    def classification(self, cutoff=0.0):
        """[(categoría, t, ley, metal)] sobre la ley de corte (metal en t; ley en % -> /100)."""
        from .estimation import CLASSES

        if self.blocks is None:
            return []
        g, c = self.blocks.cell_data["grade"], self.blocks.cell_data["class"]
        bt = float(np.prod(self.cfg["block"])) * self.density(self.cfg["domain"])
        k = 0.01 if self.cfg["unit"] == "%" else 1.0
        out = []
        for i, name in enumerate(CLASSES, 1):
            m = (c == i) & (g >= cutoff)
            out.append((name, m.sum() * bt, float(g[m].mean()) if m.any() else 0.0, float(g[m].sum()) * bt * k))
        return out

    def validation(self):
        """Acierto del modelo en los sondajes: fracción de metros cuya unidad modelada coincide con
        la registrada -> (total, {unidad: fracción})."""
        from .model import _point_at_depth, hole_path

        hit, tot = {}, {}
        for hid, ints in self.intervals.items():
            x, y, z, az, dip = self.collars[hid]
            mds, path = hole_path(x, y, z, az, dip, self.surveys.get(hid, []))
            for f, t, lith in ints:
                if lith not in self.units or t <= f:
                    continue
                d = np.arange(f + 1.0, t, 2.0) if t - f > 2 else np.array([(f + t) / 2])
                lab = self.model.label_at(np.array([_point_at_depth(mds, path, v) for v in d]))
                hit[lith] = hit.get(lith, 0.0) + float((lab == self.units.index(lith)).mean()) * (t - f)
                tot[lith] = tot.get(lith, 0.0) + (t - f)
        return sum(hit.values()) / max(sum(tot.values()), 1e-9), {u: hit[u] / tot[u] for u in tot}

    def report(self):
        el, un = self.cfg["element"], self.cfg["unit"]
        lines = ["VOLÚMENES Y TONELAJES POR UNIDAD", f"{'Unidad':<14}{'Volumen (m3)':>16}{'Tonelaje (t)':>16}"]
        lines += [f"{u:<14}{v:>16,.0f}{t:>16,.0f}" for u, v, t in self.volume_report()]
        gt = self.grade_tonnage()
        if gt:
            smu = "" if self.cfg["smu"] == [1, 1, 1] else f"  SMU {'x'.join(map(str, self.cfg['smu']))} bloques"
            lines += ["", f"CURVA LEY-TONELAJE  dominio {self.cfg['domain']}{smu}  ({self.vario})",
                      f"{'Corte ' + el + un:>12}{'Toneladas':>16}{'Ley media':>12}{'Metal (t)':>14}"]
            lines += [f"{c:>12.2f}{t:>16,.0f}{g:>12.3f}{m:>14,.0f}" for c, t, g, m in gt]
            lines += ["", "CLASIFICACIÓN (corte 0)", f"{'Categoría':<12}{'Toneladas':>16}{'Ley media':>12}{'Metal (t)':>14}"]
            lines += [f"{n:<12}{t:>16,.0f}{g:>12.3f}{m:>14,.0f}" for n, t, g, m in self.classification()]
        if self.sims is not None:
            lines += ["", "SIMULACIÓN SGS ({} realizaciones): toneladas ≥ {:g}  P10 {:,.0f} · P50 {:,.0f} · P90 {:,.0f}".format(
                len(self.sims[1]), self.sims[0], *self.sim_percentiles())]
        if self.pit is not None:
            s = self.pit[1]
            lines += ["", "PIT ÓPTIMO (clausura máxima / Lerchs-Grossmann)",
                      f"  Mineral {s['t_mineral']:,.0f} t a {s['ley']:.3f}  ·  estéril {s['t_esteril']:,.0f} t  ·  "
                      f"razón E/M {s['razon']:.2f}  ·  valor US$ {s['valor']:,.0f}"]
        tot, per = self.validation()
        lines += ["", f"VALIDACIÓN EN SONDAJES: {tot:.1%} de los metros coinciden con el modelo"]
        lines += [f"  {u:<14}{v:>8.1%}" for u, v in per.items()]
        return "\n".join(lines)


def demo_project():
    """Proyecto del yacimiento sintético (geoform/data); genera los datos si faltan."""
    from . import synth

    path = os.path.join(DATA_DIR, "demo.geoform")
    if not os.path.exists(os.path.join(DATA_DIR, "collars.csv")):
        synth.generate(DATA_DIR)
    if os.path.exists(path):
        return Project.open(path)
    p = Project(path, name="Demo Pórfido Cu", assays="assays.csv", topography="terrain.asc",
                satellite="satellite.png", stratigraphy=synth.STRAT, intrusions=[synth.INTRUSION],
                veins=[synth.VEIN], faults=[synth.FAULT], domain=synth.INTRUSION,
                density={"Porfido": 2.7, "Cobertura": 2.0, "Veta": 2.9})
    p.save()
    return p


def demo():
    import tempfile

    p = demo_project().load()
    p.cfg["cell"] = 15.0
    p.log = lambda *_: None
    p.build()
    vols = dict((u, v) for u, v, _ in p.volume_report())
    assert all(v > 0 for v in vols.values()), vols
    gt = p.grade_tonnage()
    assert gt[0][1] >= gt[-1][1] and gt[-1][2] >= gt[0][2], gt  # corte sube -> menos t, más ley
    cls = p.classification()
    assert abs(sum(t for _, t, _, _ in cls) - gt[0][1]) / gt[0][1] < 0.01, (cls, gt[0])  # categorías suman el total
    assert p.validation()[0] > 0.9, p.validation()
    p.cfg["smu"] = [2, 2, 2]
    smu = p.grade_tonnage()
    assert abs(smu[0][1] - gt[0][1]) / gt[0][1] < 0.3 and smu[0][2] <= gt[0][2], (smu[0], gt[0])  # dilución
    p.cfg["simulations"] = 2
    p.simulate()
    lo, _, hi = p.sim_percentiles()
    assert lo <= hi and 0 <= np.nanmin(p.blocks.cell_data["prob"]) <= np.nanmax(p.blocks.cell_data["prob"]) <= 1
    with tempfile.TemporaryDirectory() as tmp:
        q = Project.open(p.save(os.path.join(tmp, "x.geoform")))
        assert json.dumps(q.cfg["faults"]) == json.dumps(p.cfg["faults"]) and os.path.exists(q.file("collars"))
    print("project: OK\n" + p.report())


if __name__ == "__main__":
    demo()
