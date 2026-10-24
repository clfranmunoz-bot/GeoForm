"""Modelo geológico implícito (estilo Leapfrog): estratigrafía + fallas + intrusivos.

Cada contacto es un campo de distancia firmada:
  - estratigrafía: superficies 2.5D z=f(x,y) (TPS) desde los puntos de contacto;
    el primer contacto bajo el terreno se interpola como espesor bajo la topografía;
  - fallas: el dominio se parte en bloques y cada bloque interpola sus contactos
    solo con los datos de su lado (el desplazamiento sale de los datos);
  - intrusivos: cuerpo cerrado por RBF 3D desde muestras firmadas a lo largo de
    los pozos; corta (resta) a la estratigrafía.
Cada unidad es un sólido = intersección (min) de campos; su isosuperficie 0 es el
volumen cerrado (marching cubes).

Coordenadas del motor: z = profundidad = -elevación.
"""
import itertools

import numpy as np
from scipy.interpolate import RBFInterpolator, RegularGridInterpolator

from .model import _point_at_depth, hole_path

CAP = 30.0  # distancia máx. (m) de las muestras al contacto; acota el campo lejos de los datos


def hole_samples(collars, surveys, intervals, inside, use, step=10.0):
    """Muestras (pts (N,3), vals (N,)) de distancia firmada a lo largo de los pozos.

    inside(lith) -> True si el intervalo está del lado positivo del contacto;
    use(lith) -> False para ignorar el intervalo (p. ej. un intrusivo que corta).
    Contacto = frontera entre intervalos usados contiguos de distinto lado."""
    pts, vals = [], []
    for hid, ints in intervals.items():
        x, y, z, az, dip = collars[hid]
        mds, path = hole_path(x, y, z, az, dip, surveys.get(hid, []))
        segs = [(f, t, inside(l)) for f, t, l in ints if use(l)]
        contacts = [a[1] for a, b in zip(segs, segs[1:]) if a[2] != b[2] and abs(a[1] - b[0]) < 1e-6]
        for c in contacts:
            pts.append(_point_at_depth(mds, path, c))
            vals.append(0.0)
        for f, t, side in segs:
            for d in np.arange(f + step / 2, t, step):
                dist = min((abs(d - c) for c in contacts), default=CAP)
                pts.append(_point_at_depth(mds, path, d))
                vals.append(min(dist, CAP) if side else -min(dist, CAP))
    return np.asarray(pts, float).reshape(-1, 3), np.asarray(vals, float)


def fit_field(pts, vals):
    """RBF thin-plate suavizado: campo C1 (sin conos en los pozos como el kernel lineal)."""
    pts, idx = np.unique(np.round(pts, 3), axis=0, return_index=True)
    return RBFInterpolator(pts, vals[idx], kernel="thin_plate_spline", smoothing=2.0, degree=1)


def plane_field(fault):
    """Campo de un plano de falla {point (x,y,elev), dip_direction, dip}: >0 bloque colgante."""
    dd, dip = np.radians(fault["dip_direction"]), np.radians(fault["dip"])
    n = np.array([np.sin(dd) * np.sin(dip), np.cos(dd) * np.sin(dip), -np.cos(dip)])  # z motor = -elev
    p0 = np.array([fault["point"][0], fault["point"][1], -fault["point"][2]])
    return lambda p: (np.asarray(p, float) - p0) @ n


def topo_field(dem=None, collars=None):
    """T(p) = profundidad bajo el terreno (>0 subsuelo). dem = (xs, ys, Z elev) o collars."""
    if dem is not None:
        xs, ys, Z = dem
        f = RegularGridInterpolator((xs, ys), Z, bounds_error=False, fill_value=None)
        return lambda p: p[:, 2] + f(p[:, :2])
    c = np.array([v[:3] for v in collars.values()], float)
    g = RBFInterpolator(c[:, :2], -c[:, 2], kernel="linear", smoothing=1.0)
    return lambda p: p[:, 2] + g(p[:, :2])


class GeoModel:
    """strat: unidades de techo a base (joven -> viejo). intrusions: cuerpos que cortan.
    faults: planos (ver plane_field). dem: (xs, ys, Z) en elevación o None."""

    def __init__(self, collars, surveys, intervals, strat, intrusions=(), faults=(), dem=None, cell=10.0):
        self.collars, self.surveys, self.intervals = collars, surveys, intervals
        self.strat, self.intrusions, self.faults = list(strat), list(intrusions), list(faults)
        self.units = self.strat + self.intrusions
        self.dem, self.cell = dem, cell

    # -- campos ---------------------------------------------------------------------
    def _blocks(self):
        """[(signos, side_field)] un bloque por combinación de lados de falla."""
        ff = [plane_field(f) for f in self.faults]
        out = []
        for signs in itertools.product((1, -1), repeat=len(ff)):
            def side(p, signs=signs):
                return np.min([s * f(p) for s, f in zip(signs, ff)], axis=0) if ff else np.full(len(p), CAP)
            out.append((signs, side))
        return out

    def _contact_field(self, k, blocks, T):
        """Techo de strat[k] (>0 debajo), una superficie 2.5D por bloque de falla."""
        below = set(self.strat[k:])
        pts, vals = hole_samples(self.collars, self.surveys, self.intervals,
                                 lambda l: l in below, lambda l: l in self.strat)
        pts = pts[vals == 0]
        if len(pts) < 3:
            raise ValueError(f"muy pocos contactos para el techo de {self.strat[k]} ({len(pts)})")
        rel = k == 1
        zc = T(pts) if rel else pts[:, 2]  # espesor bajo topo, o profundidad
        fields = []
        for _signs, side in blocks:
            m = side(pts) > 0
            sel = m if m.sum() >= 6 else np.ones(len(pts), bool)
            xy, idx = np.unique(np.round(pts[sel, :2], 2), axis=0, return_index=True)
            g = RBFInterpolator(xy, zc[sel][idx], kernel="thin_plate_spline", smoothing=1.0, degree=1)
            fields.append((lambda P, g=g: T(P) - g(P[:, :2])) if rel else (lambda P, g=g: P[:, 2] - g(P[:, :2])))
        return fields

    def _body_field(self, unit, P):
        """Cuerpo cerrado (>0 dentro) por RBF 3D, evaluado solo cerca de sus datos."""
        pts, vals = hole_samples(self.collars, self.surveys, self.intervals,
                                 lambda l: l == unit, lambda l: True)
        inside = pts[vals >= 0]
        if len(inside) == 0:
            return np.full(len(P), -CAP)
        lo, hi = inside.min(axis=0) - 3 * CAP, inside.max(axis=0) + 3 * CAP
        keep = np.all((pts > lo - CAP) & (pts < hi + CAP), axis=1)
        near = np.all((P > lo) & (P < hi), axis=1)
        out = np.full(len(P), -CAP)
        out[near] = fit_field(pts[keep], vals[keep])(P[near])
        return out

    def build(self):
        import pyvista as pv

        xyz = np.array([c[:3] for c in self.collars.values()], float)
        depth = max((s[-1][0] for s in self.surveys.values() if s), default=200.0)
        T = topo_field(self.dem, self.collars)
        c = self.cell
        sp = np.array([c, c, c / 2])  # z más fino: capas delgadas (cobertura) sin aliasing
        self.spacing = sp
        lo = np.array([xyz[:, 0].min(), xyz[:, 1].min(), xyz[:, 2].min() - 2 * c])
        hi = np.array([xyz[:, 0].max(), xyz[:, 1].max(), xyz[:, 2].max() + 0.9 * depth])
        dims = np.ceil((hi - lo) / sp).astype(int) + 1
        grid = pv.ImageData(dimensions=dims, spacing=sp, origin=lo)
        P = np.asarray(grid.points)

        t = T(P)
        blocks = self._blocks()
        sides = [side(P) for _s, side in blocks]
        tops = [None] + [[f(P) for f in self._contact_field(k, blocks, T)] for k in range(1, len(self.strat))]

        solids = {}
        for k, u in enumerate(self.strat):
            per_block = []
            for b, side in enumerate(sides):
                s = np.minimum(t, side)
                if tops[k] is not None:
                    s = np.minimum(s, tops[k][b])
                if k + 1 < len(self.strat):
                    s = np.minimum(s, -tops[k + 1][b])
                per_block.append(s)
            solids[u] = np.max(per_block, axis=0)
        for j, u in enumerate(self.intrusions):
            body = self._body_field(u, P)
            for v in self.strat + self.intrusions[:j]:
                solids[v] = np.minimum(solids[v], -body)
            solids[u] = np.minimum(body, t)

        self.grid, self.topo, self.solids = grid, T, solids
        self.fault_values = [plane_field(f)(P) for f in self.faults]
        stack = np.stack([solids[u] for u in self.units])
        self.labels = np.where(t > 0, np.argmax(stack, axis=0), -1)  # -1 = aire
        grid.point_data["litho"] = self.labels
        grid.point_data["topo"] = t
        return self

    # -- productos ------------------------------------------------------------------
    def volumes(self):
        """{unidad: m3} por conteo de nodos (cada nodo representa un vóxel)."""
        v = float(np.prod(self.spacing))
        return {u: float((self.labels == k).sum()) * v for k, u in enumerate(self.units)}

    def solid_mesh(self, unit):
        """Sólido cerrado de la unidad (isosuperficie 0, bordes del dominio tapados)."""
        g = self.grid.copy()
        s = self.solids[unit].reshape(g.dimensions, order="F").copy()
        s[[0, -1], :, :] = s[:, [0, -1], :] = -1.0  # tapa laterales -> sólido cerrado
        s[:, :, [0, -1]] = -1.0
        g.point_data["s"] = s.ravel(order="F")
        m = g.contour([0.0], scalars="s")
        return m.smooth_taubin(n_iter=20) if m.n_points else m

    def fault_mesh(self, i):
        """Superficie de falla recortada al subsuelo y al dominio."""
        g = self.grid.copy()
        g.point_data["f"] = self.fault_values[i]
        m = g.contour([0.0], scalars="f")
        return m.clip_scalar(scalars="topo", value=0.0, invert=False) if m.n_points else m

    def block_grid(self):
        """ImageData de vóxeles con cell_data 'litho' (para bloques / cortes)."""
        import pyvista as pv

        g, sp = self.grid, self.spacing
        vox = pv.ImageData(dimensions=np.array(g.dimensions) + 1, spacing=sp,
                           origin=np.array(g.origin) - sp / 2)
        vox.cell_data["litho"] = self.labels
        return vox

    def label_at(self, pts):
        """Unidad (índice, -1 aire) en puntos arbitrarios: vecino más cercano en la grilla."""
        g = self.grid
        ijk = np.rint((np.asarray(pts, float) - g.origin) / self.spacing).astype(int)
        ijk = np.clip(ijk, 0, np.array(g.dimensions) - 1)
        nx, ny, _ = g.dimensions
        return self.labels[ijk[:, 0] + nx * (ijk[:, 1] + ny * ijk[:, 2])]


def demo():
    """Datos sintéticos con verdad conocida -> el modelo debe reproducir la litología."""
    import os
    import tempfile

    from . import synth
    from .app import load_project
    from .topography import load_dem

    with tempfile.TemporaryDirectory() as tmp:
        synth.generate(tmp)
        collars, surveys, intervals, _ = load_project(*(os.path.join(tmp, f) for f in ("collars.csv", "surveys.csv", "intervals.csv")))
        dem = load_dem(os.path.join(tmp, "terrain.asc"))
    m = GeoModel(collars, surveys, intervals, synth.STRAT, [synth.INTRUSION], [synth.FAULT],
                 dem=dem, cell=12.0).build()

    rng = np.random.default_rng(3)
    p = np.column_stack([rng.uniform(1050, 1550, 4000), rng.uniform(2050, 2550, 4000), rng.uniform(100, 520, 4000)])
    truth = np.array([synth.lithology(*q) if q[2] < synth.topo_elev(q[0], q[1]) else None for q in p])
    ok = truth != None  # noqa: E711
    p_m = p[ok] * [1, 1, -1]
    pred = np.array(m.units)[m.label_at(p_m)]
    acc = float((pred == truth[ok]).mean())
    assert acc > 0.85, acc
    vols = m.volumes()
    assert all(v > 0 for v in vols.values()), vols
    print(f"geomodel: OK  acierto litologico {acc:.1%} en {ok.sum()} puntos; "
          + ", ".join(f"{u} {v / 1e6:.1f} Mm3" for u, v in vols.items()))
    return m


if __name__ == "__main__":
    demo()
