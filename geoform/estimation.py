"""Estimación de recursos: compósitos por dominio, variografía, kriging en
bloques restringido al dominio geológico y curva ley-tonelaje."""
import numpy as np

from .grade import composite
from .kriging import ordinary_kriging_3d
from .model import _point_at_depth, hole_path


def domain_composites(collars, surveys, intervals, assays, domain=None, length=10.0):
    """Compósitos de `length` m; con domain, solo los cuyo punto medio cae en esa litología.
    -> (xyz (N,3), values (N,), hole_ids (N,))."""
    xyz, vals, hids = [], [], []
    for hid, rows in assays.items():
        if hid not in collars:
            continue
        x, y, z, az, dip = collars[hid]
        mds, pts = hole_path(x, y, z, az, dip, surveys.get(hid, []))
        f, t, v = composite(*zip(*rows), length)
        for a, b, g in zip(f, t, v):
            mid = (a + b) / 2
            if np.isnan(g):
                continue
            if domain and not any(i0 <= mid < i1 and l == domain for i0, i1, l in intervals.get(hid, [])):
                continue
            xyz.append(_point_at_depth(mds, pts, mid))
            vals.append(g)
            hids.append(hid)
    return np.asarray(xyz, float).reshape(-1, 3), np.asarray(vals, float), np.asarray(hids)


def experimental_variogram(xyz, vals, lag, n_lags=12, direction=None, tol=22.5):
    """Semivariograma experimental. direction=None omni | 'horizontal' | 'vertical'.
    -> (h medio, gamma, n pares) por lag (lags vacíos descartados)."""
    from scipy.spatial.distance import pdist

    d = pdist(xyz)
    g = 0.5 * pdist(vals[:, None], "sqeuclidean")
    if direction:
        dz = pdist(xyz[:, 2:3])
        ang = np.degrees(np.arcsin(np.clip(dz / np.maximum(d, 1e-9), 0, 1)))  # desde la horizontal
        keep = ang <= tol if direction == "horizontal" else ang >= 90 - tol
        d, g = d[keep], g[keep]
    k = np.floor(d / lag).astype(int)
    m = k < n_lags
    n = np.bincount(k[m], minlength=n_lags)
    hs = np.bincount(k[m], d[m], n_lags) / np.maximum(n, 1)
    gs = np.bincount(k[m], g[m], n_lags) / np.maximum(n, 1)
    ok = n > 0
    return hs[ok], gs[ok], n[ok]


def spherical(h, nugget, sill, range_):
    h = np.asarray(h, float)
    r = np.clip(h / range_, 0, 1)
    return np.where(h > 0, nugget + (sill - nugget) * (1.5 * r - 0.5 * r ** 3), 0.0)


def fit_spherical(h, g, n, var):
    """Ajuste por mínimos cuadrados ponderados por n pares. -> (nugget, sill, range)."""
    from scipy.optimize import curve_fit

    p0 = (0.1 * var, var, max(h.max() / 2, 1.0))
    bounds = ([0, 1e-9, 1.0], [var * 2, var * 3, h.max() * 3])
    try:
        p, _ = curve_fit(spherical, h, g, p0=p0, sigma=1 / np.sqrt(n), bounds=bounds, maxfev=5000)
    except (RuntimeError, ValueError):
        p = p0
    nug, sill, rng = (float(v) for v in p)
    return min(nug, sill), sill, rng


class Variogram:
    """Modelo esférico con anisotropía horizontal/vertical ajustado a los datos."""

    def __init__(self, xyz, vals, lag=None):
        self.var = float(np.var(vals))
        ext = float(np.ptp(xyz, axis=0).max())
        self.lag = lag or ext / 15
        self.omni = experimental_variogram(xyz, vals, self.lag)
        self.horiz = experimental_variogram(xyz, vals, self.lag, direction="horizontal")
        self.vert = experimental_variogram(xyz, vals, self.lag / 2, n_lags=16, direction="vertical")
        self.nugget, self.sill, self.range_h = fit_spherical(*self.omni, self.var)
        if len(self.horiz[0]) >= 3:
            _n, _s, self.range_h = fit_spherical(*self.horiz, self.var)
        self.range_v = fit_spherical(*self.vert, self.var)[2] if len(self.vert[0]) >= 3 else self.range_h

    @property
    def aniso(self):
        r = max(self.range_h, self.range_v)
        return (self.range_h / r, self.range_h / r, self.range_v / r)

    def kriging_kwargs(self):
        return dict(range_=max(self.range_h, self.range_v), nugget=self.nugget, sill=self.sill, aniso=self.aniso)

    def __str__(self):
        return (f"esférico: nugget={self.nugget:.4f} sill={self.sill:.4f} "
                f"alcance H={self.range_h:.0f} m V={self.range_v:.0f} m")


def domain_block_model(model, domain, xyz, vals, block=(10.0, 10.0, 10.0), vario=None, method="kriging"):
    """Bloques regulares dentro del sólido `domain` del GeoModel, estimados con
    los compósitos del dominio. -> pv.ImageData con cell_data 'grade' (NaN fuera)."""
    import pyvista as pv

    from .kriging import idw

    k = model.units.index(domain)
    inside = model.grid.points[model.labels == k]
    lo = inside.min(axis=0) - np.asarray(block)
    hi = inside.max(axis=0) + np.asarray(block)
    dims = np.ceil((hi - lo) / block).astype(int) + 1
    vox = pv.ImageData(dimensions=dims, spacing=block, origin=lo)
    centers = np.asarray(vox.cell_centers().points)
    mask = model.label_at(centers) == k
    grade = np.full(len(centers), np.nan)
    if method == "kriging":
        kw = vario.kriging_kwargs() if vario is not None else {}
        grade[mask] = ordinary_kriging_3d(xyz, vals, centers[mask], n_neighbors=24, **kw)
    else:
        grade[mask] = idw(xyz, vals, centers[mask], n_neighbors=12)
    vox.cell_data["grade"] = grade
    vox.cell_data["domain"] = mask.astype(np.uint8)
    vox.cell_data["class"] = classify(xyz, centers, mask, vario)
    return vox


CLASSES = ("Medido", "Indicado", "Inferido")


def classify(xyz, centers, mask, vario, n=3):
    """Categoría por cercanía de datos: distancia al n-ésimo compósito más cercano vs. alcance
    del variograma (<= 1/3 Medido, <= 2/3 Indicado, resto Inferido). 0 = fuera del dominio.
    shortcut: criterio geométrico simple (no varianza de kriging ni nº de sondajes), suficiente
    para un primer reporte; para un reporte JORC/NI 43-101 usar los criterios del QP."""
    from scipy.spatial import cKDTree

    r = vario.range_h if vario is not None and vario.range_h else 100.0
    out = np.zeros(len(centers), np.uint8)
    if mask.any():
        d = cKDTree(xyz).query(centers[mask], k=min(n, len(xyz)))[0]
        d = d[:, -1] if d.ndim > 1 else d
        out[mask] = np.where(d <= r / 3, 1, np.where(d <= 2 * r / 3, 2, 3))
    return out


def grade_shell(model, xyz, vals, cutoff):
    """Envolvente de ley (modelo numérico estilo Leapfrog): RBF lineal de todos los compósitos,
    isosuperficie `cutoff`, recortada al subsuelo. -> pv.PolyData (coords. motor)."""
    import pyvista as pv
    from scipy.interpolate import RBFInterpolator

    lo, hi = np.array(model.grid.bounds).reshape(3, 2).T
    step = 2 * model.cell  # grilla gruesa: el RBF global es caro y la envolvente es suave
    g = pv.ImageData(dimensions=np.ceil((hi - lo) / step).astype(int) + 1, spacing=[step] * 3, origin=lo)
    P = np.asarray(g.points)
    f = RBFInterpolator(xyz, vals, kernel="linear", smoothing=len(vals) * 0.01, neighbors=64)
    g.point_data["g"] = f(P)
    g.point_data["topo"] = model.topo(P)
    m = g.contour([cutoff], scalars="g")
    if m.n_points:
        m = m.clip_scalar(scalars="topo", value=0.0, invert=False)
    return m.smooth_taubin(n_iter=20) if m.n_points else m


def stats(vals):
    """Estadística descriptiva de compósitos."""
    v = np.asarray(vals, float)
    return {"n": len(v), "media": v.mean(), "desv": v.std(), "CV": v.std() / v.mean() if v.mean() else 0.0,
            "mín": v.min(), "P50": np.percentile(v, 50), "P95": np.percentile(v, 95),
            "P99": np.percentile(v, 99), "máx": v.max()}


def swath(xyz, vals, blocks, axis, width):
    """Swath plot: media de compósitos vs. media de bloques por franjas de `width` m a lo largo de
    `axis` (0 X, 1 Y, 2 Z elevación). -> (centros, media compósitos, media bloques, n compósitos)."""
    c = np.asarray(blocks.cell_centers().points)
    gb = blocks.cell_data["grade"]
    ok = np.isfinite(gb)
    sgn = -1 if axis == 2 else 1  # z motor = -elev
    a, b = sgn * xyz[:, axis], sgn * c[ok, axis]
    edges = np.arange(np.floor(min(a.min(), b.min()) / width) * width, max(a.max(), b.max()) + width, width)
    ia, ib = np.digitize(a, edges), np.digitize(b, edges)
    rows = []
    for i in range(1, len(edges)):
        ma, mb = ia == i, ib == i
        if ma.any() or mb.any():
            rows.append((edges[i - 1] + width / 2, vals[ma].mean() if ma.any() else np.nan,
                         gb[ok][mb].mean() if mb.any() else np.nan, int(ma.sum())))
    return tuple(np.array(r) for r in zip(*rows))


def grade_tonnage(grades, block_volume, density, cutoffs):
    """Tabla [(ley de corte, toneladas, ley media, metal t)] sobre bloques estimados."""
    g = np.asarray(grades, float)
    g = g[np.isfinite(g)]
    rows = []
    for c in cutoffs:
        sel = g >= c
        tonnes = sel.sum() * block_volume * density
        mean = float(g[sel].mean()) if sel.any() else 0.0
        rows.append((float(c), float(tonnes), mean, tonnes * mean / 100.0))
    return rows


def demo():
    rng = np.random.default_rng(0)
    # variograma de un campo con alcance conocido: suma de gaussianas de ~30 m
    xyz = rng.uniform(0, 400, (900, 3))
    centers = rng.uniform(0, 400, (60, 3))
    vals = np.exp(-((xyz[:, None, :] - centers[None]) ** 2).sum(-1) / (2 * 30.0 ** 2)).sum(1)
    v = Variogram(xyz, vals)
    assert 0 <= v.nugget < 0.3 * v.sill, v
    assert 30 < v.range_h < 250, v

    # ley-tonelaje: corte 0 -> todos los bloques; sube la ley media al subir el corte
    g = np.array([0.1, 0.5, 1.0, np.nan])
    t = grade_tonnage(g, 1000.0, 2.5, [0.0, 0.4])
    assert t[0][1] == 3 * 2500 and abs(t[0][2] - 0.5333) < 1e-3, t
    assert t[1][1] == 2 * 2500 and t[1][2] > t[0][2], t

    assert spherical(0, 0.1, 1, 50) == 0 and abs(spherical(80, 0.1, 1, 50) - 1) < 1e-12
    print(f"estimation: OK  {v}")


if __name__ == "__main__":
    demo()
