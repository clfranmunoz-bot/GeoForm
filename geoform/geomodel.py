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


DRIFT = {"linear": 1, "quadratic": 2}  # grado del polinomio de tendencia del RBF (TPS exige >= 1)


def aniso_matrix(bearing=0.0, plunge=0.0, ratios=(1.0, 1.0, 1.0)):
    """Elipsoide de anisotropía -> A (3x3) en coords. motor: P @ A.T lleva al espacio isótropo.
    Eje mayor con rumbo `bearing` (desde el norte) e inmersión `plunge` (hacia abajo); `ratios` =
    alcances relativos (mayor, intermedio, menor): más alcance = más continuidad en ese eje."""
    b, p = np.radians(bearing), np.radians(plunge)
    u = np.array([np.sin(b) * np.cos(p), np.cos(b) * np.cos(p), np.sin(p)])  # z motor = profundidad
    v = np.array([np.cos(b), -np.sin(b), 0.0])
    return np.array([u, v, np.cross(u, v)]) / np.asarray(ratios, float)[:, None]


def fit_field(pts, vals, degree=1, A=None):
    """RBF thin-plate suavizado: campo C1 (sin conos en los pozos como el kernel lineal).
    degree = drift (1 lineal, 2 cuadrático); A = matriz de anisotropía (aniso_matrix)."""
    pts, idx = np.unique(np.round(pts, 3), axis=0, return_index=True)
    if A is None:
        return RBFInterpolator(pts, vals[idx], kernel="thin_plate_spline", smoothing=2.0, degree=degree)
    f = RBFInterpolator(pts @ A.T, vals[idx], kernel="thin_plate_spline", smoothing=2.0, degree=degree)
    return lambda P: f(np.asarray(P) @ A.T)


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

    def __init__(self, collars, surveys, intervals, strat, intrusions=(), faults=(), dem=None, cell=10.0,
                 picks=None, volumes=(), veins=(), mesh_refinement=1,
                 drift="linear", anisotropy=None):
        """picks: {unidad: [[x, y, elev], ...]} contactos trazados a mano para el techo de la unidad.
        volumes: [{name, top, bottom}] volúmenes entre dos superficies (nombres de self.surfaces).
        mesh_refinement: 1 = sin subdividir (rápido), 2 = Loop, 3 = Butterfly (suaviza contactos voxel).
        drift: "linear" | "quadratic" (tendencia de los RBF de contactos, intrusivos y vetas).
        anisotropy: {bearing, plunge, ratios} para intrusivos (3D) y contactos (rumbo y razón en planta).
        """
        self.collars, self.surveys, self.intervals = collars, surveys, intervals
        self.picks, self.custom_volumes = picks or {}, list(volumes)
        self.veins = [v for v in veins if v not in strat and v not in intrusions]
        self.strat, self.intrusions, self.faults = list(strat), list(intrusions), list(faults)
        self.units = self.strat + self.intrusions + self.veins
        self.dem, self.cell = dem, cell
        self.mesh_refinement = mesh_refinement
        self.degree = DRIFT[drift]
        an = {"bearing": 0.0, "plunge": 0.0, "ratios": [1.0, 1.0, 1.0], **(anisotropy or {})}
        iso = an["ratios"][0] == an["ratios"][1] == an["ratios"][2]
        self.A = None if iso else aniso_matrix(an["bearing"], an["plunge"], an["ratios"])
        b = np.radians(an["bearing"])  # contactos 2.5D: solo rumbo y razón mayor/intermedio en planta
        r = an["ratios"]
        self.A2 = None if r[0] == r[1] else np.array([[np.sin(b), np.cos(b)], [np.cos(b), -np.sin(b)]]) / np.array(r[:2])[:, None]

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
        extra = np.asarray(self.picks.get(self.strat[k], []), float).reshape(-1, 3) * [1, 1, -1]
        pts = np.vstack([pts, extra])
        if len(pts) < 3:
            raise ValueError(f"muy pocos contactos para el techo de {self.strat[k]} ({len(pts)})")
        rel = k == 1
        zc = T(pts) if rel else pts[:, 2]  # espesor bajo topo, o profundidad
        fields = []
        for _signs, side in blocks:
            m = side(pts) > 0
            sel = m if m.sum() >= 6 else np.ones(len(pts), bool)
            xy, idx = np.unique(np.round(pts[sel, :2], 2), axis=0, return_index=True)
            if self.A2 is None:
                g = RBFInterpolator(xy, zc[sel][idx], kernel="thin_plate_spline", smoothing=1.0, degree=self.degree)
            else:
                g0 = RBFInterpolator(xy @ self.A2.T, zc[sel][idx], kernel="thin_plate_spline", smoothing=1.0, degree=self.degree)
                g = lambda q, g0=g0: g0(q @ self.A2.T)
            fields.append((lambda P, g=g: T(P) - self._xy_eval(g, P)) if rel else (lambda P, g=g: P[:, 2] - self._xy_eval(g, P)))
        return fields

    def _xy_eval(self, g, P):
        """g(x, y) en P; en la grilla del modelo evalúa una vez por columna (nx*ny) y repite en z."""
        P0 = getattr(self, "_P", None)
        if P0 is not None and P is P0:
            nx, ny, nz = self._dims
            return np.tile(g(P[:nx * ny, :2]), nz)
        return g(P[:, :2])

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
        # el RBF 3D es caro: se evalúa en una grilla gruesa (2 celdas) y se interpola trilineal
        step = 2 * self.cell
        axes = [np.arange(lo[i], hi[i] + step, step) for i in range(3)]
        G = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        coarse = fit_field(pts[keep], vals[keep], self.degree, self.A)(G).reshape([len(a) for a in axes])
        out[near] = RegularGridInterpolator(axes, coarse)(P[near])
        return out

    def _vein(self, unit):
        """Veta estilo Leapfrog: techo (HW) y piso (FW) de cada intersección -> plano medio por PCA;
        HW y FW se interpolan como w(u, v) sobre ese plano (TPS). Límite lateral = distancia a la
        envolvente convexa de las intersecciones + medio espaciado. -> dict con lo necesario para campo y malla."""
        from scipy.spatial import cKDTree

        hw, fw = [], []
        for hid, ints in self.intervals.items():
            x, y, z, az, dip = self.collars[hid]
            mds, path = hole_path(x, y, z, az, dip, self.surveys.get(hid, []))
            for f, t, lith in ints:
                if lith == unit:
                    hw.append(_point_at_depth(mds, path, f))
                    fw.append(_point_at_depth(mds, path, t))
        if len(hw) < 4:
            return None
        hw, fw = np.array(hw), np.array(fw)
        mid = (hw + fw) / 2
        c = mid.mean(axis=0)
        _, _, vt = np.linalg.svd(mid - c)
        e1, e2, n = vt  # n = normal del plano medio (menor varianza)
        uv = np.column_stack([(mid - c) @ e1, (mid - c) @ e2])
        a, b = (hw - c) @ n, (fw - c) @ n
        top, bot = np.maximum(a, b), np.minimum(a, b)  # lado + / lado - del plano medio
        kw = dict(kernel="thin_plate_spline", smoothing=1.0, degree=self.degree)
        tree = cKDTree(uv)
        spacing = np.median(tree.query(uv, k=2)[0][:, 1])
        from scipy.spatial import Delaunay
        return {"c": c, "e1": e1, "e2": e2, "n": n, "uv": uv, "tree": tree, "R": 0.5 * spacing, "hull": Delaunay(uv),
                "top": RBFInterpolator(uv, top, **kw), "bot": RBFInterpolator(uv, bot, **kw)}

    def _vein_field(self, V, P):
        """>0 dentro de la veta (metros), acotado lateralmente."""
        d = P - V["c"]
        uv = np.column_stack([d @ V["e1"], d @ V["e2"]])
        w = d @ V["n"]
        out = np.full(len(P), -CAP)
        lat = self._vein_lateral(V, uv)
        near = lat > -2 * CAP
        out[near] = np.minimum(np.minimum(w[near] - V["bot"](uv[near]), V["top"](uv[near]) - w[near]), lat[near])
        return out

    @staticmethod
    def _vein_lateral(V, uv):
        """>0 dentro del contorno de la veta: envolvente convexa de las intersecciones + margen R."""
        lat = V["R"] - V["tree"].query(uv)[0]
        return np.where(V["hull"].find_simplex(uv) >= 0, np.maximum(lat, CAP), lat)

    def vein_mesh(self, unit, step=None):
        """Sólido cerrado de la veta: lámina HW/FW muestreada sobre el plano medio (no depende de
        la resolución de la grilla, así una veta de 5 m no se pierde entre celdas de 10 m)."""
        import pyvista as pv

        V = self.vein_info[unit]
        step = step or self.cell / 2
        lo, hi = V["uv"].min(axis=0) - V["R"], V["uv"].max(axis=0) + V["R"]
        us, vs = np.arange(lo[0], hi[0] + step, step), np.arange(lo[1], hi[1] + step, step)
        U, W = np.meshgrid(us, vs, indexing="ij")
        uv = np.column_stack([U.ravel(), W.ravel()])
        t, b = V["top"](uv), V["bot"](uv)
        b = np.minimum(b, t - 0.5)  # espesor mínimo 0.5 m
        layers = [V["c"] + uv[:, :1] * V["e1"] + uv[:, 1:] * V["e2"] + w[:, None] * V["n"] for w in (b, t)]
        X = np.stack([L.reshape(len(us), len(vs), 3) for L in layers], axis=2)
        g = pv.StructuredGrid(X[..., 0], X[..., 1], X[..., 2])
        inside = self._vein_lateral(V, uv) > 0
        cm = (inside.reshape(len(us), len(vs))[:-1, :-1] & inside.reshape(len(us), len(vs))[1:, 1:])
        g.cell_data["in"] = cm.ravel(order="F").astype(float)
        T = self.topo(g.cell_centers().points)
        g.cell_data["in"] *= (T > 0)  # bajo el terreno
        s = g.threshold(0.5, scalars="in").extract_surface(algorithm="dataset_surface")
        return s.smooth_taubin(n_iter=10) if s.n_points else s

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
        self._P, self._dims = P, tuple(dims)

        t = T(P)
        blocks = self._blocks()
        sides = [side(P) for _s, side in blocks]
        tops = [None] + [[f(P) for f in self._contact_field(k, blocks, T)] for k in range(1, len(self.strat))]

        solids, raw = {}, {}  # raw: campo por bloque sin la falla (la malla se corta exacto en el plano)
        for k, u in enumerate(self.strat):
            per_block = []
            for b, side in enumerate(sides):
                s = t
                if tops[k] is not None:
                    s = np.minimum(s, tops[k][b])
                if k + 1 < len(self.strat):
                    s = np.minimum(s, -tops[k + 1][b])
                per_block.append(s)
            raw[u] = per_block
            solids[u] = np.max([np.minimum(s, side) for s, side in zip(per_block, sides)], axis=0)
        for j, u in enumerate(self.intrusions):
            body = self._body_field(u, P)
            for v in self.strat + self.intrusions[:j]:
                solids[v] = np.minimum(solids[v], -body)
                if v in raw:
                    raw[v] = [np.minimum(s, -body) for s in raw[v]]
            solids[u] = np.minimum(body, t)

        # superficies de contacto (una por techo, combinando bloques de falla) y volúmenes del usuario
        blk = np.argmax(np.stack(sides), axis=0)
        self.surfaces = {"Topografía": t}
        for k in range(1, len(self.strat)):
            self.surfaces[f"Techo {self.strat[k]}"] = np.choose(blk, tops[k])
        self.custom = {}
        for v in self.custom_volumes:
            top, bot = self.surfaces[v["top"]], self.surfaces[v["bottom"]]
            self.custom[v["name"]] = np.minimum(np.minimum(t, top), -bot)

        self.vein_info = {}
        for u in self.veins:  # las vetas cortan todo (son las más jóvenes)
            V = self._vein(u)
            body = self._vein_field(V, P) if V is not None else np.full(len(P), -CAP)
            if V is not None:
                self.vein_info[u] = V
            for v in self.strat + self.intrusions:
                solids[v] = np.minimum(solids[v], -body)
                if v in raw:
                    raw[v] = [np.minimum(s, -body) for s in raw[v]]
            solids[u] = np.minimum(body, t)

        self.grid, self.topo, self.solids, self.raw = grid, T, solids, raw
        self.block_signs = [s for s, _ in blocks]
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
        out = {u: float((self.labels == k).sum()) * v for k, u in enumerate(self.units)}
        for u in self.vein_info:  # una veta delgada se mide mejor en su propia malla cerrada
            out[u] = float(self.vein_mesh(u).volume)
        return out

    def custom_volume(self, name):
        return float((self.custom[name] > 0).sum()) * float(np.prod(self.spacing))

    def surface_mesh(self, name):
        """Malla de una superficie de contacto (isosuperficie 0), recortada al subsuelo."""
        g = self.grid.copy()
        g.point_data["f"] = self.surfaces[name]
        m = g.contour([0.0], scalars="f")
        if name != "Topografía" and m.n_points:
            m = m.clip_scalar(scalars="topo", value=0.0, invert=False)
        return m.smooth_taubin(n_iter=20) if m.n_points else m

    def solid_mesh(self, unit):
        if unit in getattr(self, "vein_info", {}):
            return self.vein_mesh(unit)
        return self._solid_mesh(unit)

    def _solid_mesh(self, unit):
        """Sólido cerrado. Con fallas, cada bloque se mallea por separado y se corta exacto en el
        plano de falla (escalón nítido, como Leapfrog) en vez de depender de la grilla."""
        if not self.faults or unit not in self.raw:
            return self._iso_mesh(self.solids[unit] if unit in self.solids else self.custom[unit])
        import pyvista as pv

        parts = []
        for signs, field in zip(self.block_signs, self.raw[unit]):
            m = self._iso_mesh(field)
            for s, f in zip(signs, self.faults):
                if not m.n_points:
                    break
                dd, dip = np.radians(f["dip_direction"]), np.radians(f["dip"])
                n = s * np.array([np.sin(dd) * np.sin(dip), np.cos(dd) * np.sin(dip), -np.cos(dip)])
                try:  # conserva el lado del bloque y tapa la cara sobre el plano
                    m = m.clip_closed_surface(normal=n, origin=(f["point"][0], f["point"][1], -f["point"][2]))
                except (RuntimeError, ValueError):  # malla no cerrada: corte abierto
                    m = m.clip(normal=-n, origin=(f["point"][0], f["point"][1], -f["point"][2]))
            if m.n_points:
                parts.append(m.extract_surface(algorithm="dataset_surface"))
        return pv.merge(parts) if parts else pv.PolyData()

    def _iso_mesh(self, field):
        g = self.grid.copy()
        s = np.asarray(field).reshape(g.dimensions, order="F").copy()
        s[[0, -1], :, :] = s[:, [0, -1], :] = -1e-3  # tapa casi en el borde: caras laterales planas, sin huecos
        s[:, :, [0, -1]] = -1e-3
        g.point_data["s"] = s.ravel(order="F")
        m = g.contour([0.0], scalars="s")
        if not m.n_points:
            return m
        # Refinamiento de malla (subdivisión) para contactos más suaves tipo Leapfrog
        # mesh_refinement: 1 = sin subdividir (rápido), 2 = Loop, 3 = Butterfly
        refinement = getattr(self, "mesh_refinement", 1)
        if refinement >= 2:
            m = m.subdivide(refinement - 1, subfilter="loop" if refinement == 2 else "butterfly")
        return m.smooth_taubin(n_iter=20, feature_smoothing=False, boundary_smoothing=False, feature_angle=50)

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

    def field_at(self, values, pts):
        """Interpolación trilineal de un campo de la grilla en puntos arbitrarios (perfiles suaves)."""
        g = self.grid
        axes = [g.origin[i] + self.spacing[i] * np.arange(g.dimensions[i]) for i in range(3)]
        f = RegularGridInterpolator(axes, np.asarray(values).reshape(g.dimensions, order="F"),
                                    bounds_error=False, fill_value=None)
        return f(np.asarray(pts, float))

    def label_at(self, pts, values=None):
        """Unidad (índice, -1 aire), o `values` de la grilla, en puntos arbitrarios: vecino más cercano."""
        g = self.grid
        ijk = np.rint((np.asarray(pts, float) - g.origin) / self.spacing).astype(int)
        ijk = np.clip(ijk, 0, np.array(g.dimensions) - 1)
        nx, ny, _ = g.dimensions
        out = (self.labels if values is None else values)[ijk[:, 0] + nx * (ijk[:, 1] + ny * ijk[:, 2])]
        if values is None:  # vetas: campo exacto, una veta de 5 m no cabe en la grilla
            for u, V in getattr(self, "vein_info", {}).items():
                inside = (self._vein_field(V, np.asarray(pts, float)) > 0) & (out >= 0)
                out = np.where(inside, self.units.index(u), out)
        return out


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
                 dem=dem, cell=12.0, veins=[synth.VEIN]).build()

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
    # veta: puntos reales dentro de la veta y dentro de la zona perforada -> el modelo debe decir Veta
    c = np.array(synth.VEIN_PLANE["center"])
    q = c + rng.uniform(-90, 90, (20000, 3))
    inv = np.array([synth.lithology(*r) == synth.VEIN for r in q])
    pv_ = np.array(m.units)[m.label_at(q[inv] * [1, 1, -1])]
    vein_hit = float((pv_ == synth.VEIN).mean())
    assert vein_hit > 0.6, vein_hit
    # superficies, volumen entre dos superficies elegidas y contacto trazado a mano
    names = list(m.surfaces)
    assert all(m.surface_mesh(n).n_points for n in names), names
    m2 = GeoModel(collars, surveys, intervals, synth.STRAT, [synth.INTRUSION], [synth.FAULT], dem=dem, cell=12.0,
                  picks={synth.STRAT[2]: [[1300, 2300, 300.0]]},
                  volumes=[{"name": "Paquete", "top": names[1], "bottom": names[-1]}]).build()
    assert m2.custom_volume("Paquete") > 0 and m2.solid_mesh("Paquete").n_points
    # anisotropía: el eje mayor (rumbo 45°, inmersión 30°) de largo 3 cae a largo 1 en el espacio isótropo
    A = aniso_matrix(45, 30, (3, 2, 1))
    u = np.array([np.sin(np.pi / 4) * np.cos(np.pi / 6), np.cos(np.pi / 4) * np.cos(np.pi / 6), 0.5])
    assert np.allclose(A @ (3 * u), [1, 0, 0]), A @ (3 * u)
    # drift cuadrático + anisotropía siguen reproduciendo la litología
    m3 = GeoModel(collars, surveys, intervals, synth.STRAT, [synth.INTRUSION], [synth.FAULT], dem=dem, cell=12.0,
                  drift="quadratic", anisotropy={"bearing": 30, "plunge": 0, "ratios": [1.5, 1, 1]}).build()
    acc3 = float((np.array(m3.units)[m3.label_at(p_m)] == truth[ok]).mean())
    assert acc3 > 0.8, acc3
    print(f"geomodel: OK  acierto litologico {acc:.1%} en {ok.sum()} puntos; veta {vein_hit:.0%}; "
          + ", ".join(f"{u} {v / 1e6:.1f} Mm3" for u, v in vols.items()))
    return m


if __name__ == "__main__":
    demo()
