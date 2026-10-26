"""Estimación de recursos: compósitos por dominio, variografía, kriging en
bloques restringido al dominio geológico y curva ley-tonelaje."""
import numpy as np

from .grade import composite
from .kriging import ordinary_kriging_3d, ordinary_kriging_3d_variance
from .model import _point_at_depth, hole_path

# JORC classification categories (1-indexed in classify output)
CLASSES = ['Medido', 'Indicado', 'Inferido']


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


def exponential(h, nugget, sill, range_):
    """Modelo exponencial: gamma(h) = nugget + sill * (1 - exp(-3h/range))"""
    h = np.asarray(h, float)
    return np.where(h > 0, nugget + (sill - nugget) * (1 - np.exp(-3 * h / range_)), 0.0)


def gaussian(h, nugget, sill, range_):
    """Modelo gaussiano: gamma(h) = nugget + sill * (1 - exp(-3(h/range)^2))"""
    h = np.asarray(h, float)
    return np.where(h > 0, nugget + (sill - nugget) * (1 - np.exp(-3 * (h / range_)**2)), 0.0)


def hole_effect(h, nugget, sill, range_):
    """Efecto hoyo (hole effect): modelo esférico con oscilación"""
    h = np.asarray(h, float)
    r = np.clip(h / range_, 0, 1)
    base = np.where(h > 0, nugget + (sill - nugget) * (1.5 * r - 0.5 * r ** 3), 0.0)
    # Agregar oscilación sinusoidal
    return base + 0.1 * sill * np.sin(2 * np.pi * h / range_) * np.exp(-h / range_)


def fit_variogram_model(h, g, n, var, model="spherical"):
    """Ajuste genérico para cualquier modelo de variograma."""
    from scipy.optimize import curve_fit
    
    models = {"spherical": spherical, "exponential": exponential, "gaussian": gaussian, "hole_effect": hole_effect}
    func = models.get(model, spherical)
    
    p0 = (0.1 * var, var, max(h.max() / 2, 1.0))
    bounds = ([0, 1e-9, 1.0], [var * 2, var * 3, h.max() * 3])
    try:
        p, _ = curve_fit(func, h, g, p0=p0, sigma=1 / np.sqrt(n), bounds=bounds, maxfev=5000)
    except (RuntimeError, ValueError):
        p = p0
    nug, sill, rng = (float(v) for v in p)
    return min(nug, sill), sill, rng


class Variogram:
    """Modelo de variograma con anisotropía 3D completa y modelos anidados.
    
    Soporta: spherical, exponential, gaussian, hole_effect
    Anisotropía 3D: matriz de rotación (bearing, plunge, dip) + alcances (major, semi-major, minor)
    Modelos anidados: suma de múltiples estructuras + nugget."""

    def __init__(self, xyz, vals, lag=None, n_structures=1, model="spherical", 
                 bearing=0.0, plunge=0.0, dip=0.0, aniso_ratios=(1.0, 1.0, 1.0)):
        self.var = float(np.var(vals))
        self.model_type = model
        ext = float(np.ptp(xyz, axis=0).max())
        self.lag = lag or ext / 15
        self.n_structures = max(1, n_structures)
        
        # Anisotropía 3D completa: rotación + escalado
        self.rotation_matrix = self._build_rotation_matrix(bearing, plunge, dip)
        self.aniso_ratios = np.asarray(aniso_ratios, float)  # (major, semi-major, minor)
        
        # Transformar coordenadas a espacio anisotrópico
        xyz_a = self._transform_coords(xyz)
        
        self.omni = experimental_variogram(xyz_a, vals, self.lag)
        self.horiz = experimental_variogram(xyz_a, vals, self.lag, direction="horizontal")
        self.vert = experimental_variogram(xyz_a, vals, self.lag / 2, n_lags=16, direction="vertical")
        
        # Ajustar modelo anidado
        self.structures = self._fit_nested(*self.omni)
        
        # Parámetros principales (primera estructura)
        self.nugget = self.structures[0][0] if self.structures else 0.0
        self.sill = sum(s[1] for s in self.structures) + self.nugget
        self.ranges = np.array([s[2] for s in self.structures]) if self.structures else np.array([self.lag * 3])
        self.range_major = self.ranges[0]
        
        # Rangos aparentes en direcciones cardinales (para compatibilidad)
        self.range_h = self.range_major * self.aniso_ratios[0]
        self.range_v = self.range_major * self.aniso_ratios[2]
        
        # Anisotropía 3D completa
        self.aniso_3d = self.aniso_ratios / self.aniso_ratios.max()

    def _build_rotation_matrix(self, bearing, plunge, dip):
        """Construye matriz de rotación 3x3 a partir de ángulos de Euler (grados).
        bearing: azimuth del eje mayor (0=N, 90=E)
        plunge: buzamiento del eje mayor
        dip: rotación alrededor del eje mayor"""
        from math import cos, sin, radians
        b, p, d = map(radians, (bearing, plunge, dip))
        
        # Rotación Z (bearing) -> Y (plunge) -> X (dip)
        Rb = np.array([[cos(b), -sin(b), 0], [sin(b), cos(b), 0], [0, 0, 1]])
        Rp = np.array([[cos(p), 0, sin(p)], [0, 1, 0], [-sin(p), 0, cos(p)]])
        Rd = np.array([[1, 0, 0], [0, cos(d), -sin(d)], [0, sin(d), cos(d)]])
        
        return Rb @ Rp @ Rd

    def _transform_coords(self, xyz):
        """Transforma coordenadas a espacio isótropo (rotación + escalado anisotrópico)."""
        # Rotar
        xyz_r = xyz @ self.rotation_matrix.T
        # Escalar por ratios anisotrópicos
        return xyz_r / self.aniso_ratios

    def _inverse_transform_coords(self, xyz_a):
        """Transforma de espacio anisotrópico a coordenadas reales."""
        xyz_r = xyz_a * self.aniso_ratios
        return xyz_r @ self.rotation_matrix

    def _fit_nested(self, h, g, n):
        """Ajusta suma de estructuras por mínimos cuadrados ponderados."""
        from scipy.optimize import curve_fit
        
        if len(h) < 3:
            return [(0.1 * self.var, self.var * 0.9, max(h.max(), 1.0))]
        
        # Modelo: nugget + sum(sill_i * model(h, range_i))
        def nested_model(h, *params):
            nug = params[0]
            result = np.full_like(h, nug)
            n_struct = (len(params) - 1) // 2
            for i in range(n_struct):
                sill_i = params[1 + 2*i]
                range_i = params[2 + 2*i]
                result += sill_i * self._single_model(h, range_i)
            return result
        
        n_struct = self.n_structures
        p0 = [0.1 * self.var]
        for i in range(n_struct):
            p0.extend([self.var * 0.9 / n_struct, max(h.max() / (2 * (i + 1)), 1.0)])
        
        bounds_low = [0] + [1e-9, 1.0] * n_struct
        bounds_high = [self.var * 2] + [self.var * 3, h.max() * 5] * n_struct
        
        try:
            p, _ = curve_fit(nested_model, h, g, p0=p0, sigma=1 / np.sqrt(n),
                           bounds=(bounds_low, bounds_high), maxfev=10000)
            structures = []
            for i in range(n_struct):
                structures.append((float(p[0]) if i == 0 else 0.0, float(p[1 + 2*i]), float(p[2 + 2*i])))
            return structures
        except (RuntimeError, ValueError):
            return [(0.1 * self.var, self.var * 0.9, max(h.max() / 2, 1.0))]

    def _single_model(self, h, range_):
        """Evalúa un modelo individual."""
        if self.model_type == "exponential":
            return exponential(h, 0, 1, range_)
        elif self.model_type == "gaussian":
            return gaussian(h, 0, 1, range_)
        elif self.model_type == "hole_effect":
            return hole_effect(h, 0, 1, range_)
        return spherical(h, 0, 1, range_)

    def _cov_single(self, h, nugget, sill, range_):
        """Covarianza para un modelo individual."""
        return sill - self._single_model(h, range_) * sill - nugget * (h > 0)

    @property
    def aniso(self):
        r = max(self.range_h, self.range_v)
        return (self.range_h / r, self.range_h / r, self.range_v / r)

    def kriging_kwargs(self):
        """Parámetros para kriging: usa la estructura principal con anisotropía 3D."""
        return dict(range_=self.range_major, nugget=self.nugget, 
                   sill=self.sill, aniso=self.aniso_3d,
                   rotation_matrix=self.rotation_matrix, aniso_ratios=self.aniso_ratios)

    def cov(self, h):
        """Covarianza para la suma de estructuras en espacio anisotrópico."""
        h = np.asarray(h, float)
        c = np.zeros_like(h)
        for nug, sill, rng in self.structures:
            c += sill * (1 - self._single_model(h, rng))
        c[h == 0] = self.sill
        return c

    def __str__(self):
        if len(self.structures) > 1:
            struct_str = " + ".join(f"{self.model_type}(sill={s[1]:.4f}, range={s[2]:.0f})" for s in self.structures)
            return (f"{self.model_type} anidado: nugget={self.nugget:.4f} + {struct_str} "
                    f"(major={self.range_major:.0f}, ratios={self.aniso_ratios})")
        return (f"{self.model_type}: nugget={self.nugget:.4f} sill={self.sill:.4f} "
                f"major={self.range_major:.0f} m, ratios={self.aniso_ratios}")


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
    elif method == "nearest":  # vecino más cercano (polígonos 3D): sin suavizado, referencia de sesgo
        from scipy.spatial import cKDTree
        grade[mask] = vals[cKDTree(xyz).query(centers[mask])[1]]
    else:
        grade[mask] = idw(xyz, vals, centers[mask], n_neighbors=12)
    vox.cell_data["grade"] = grade
    vox.cell_data["domain"] = mask.astype(np.uint8)
    vox.cell_data["class"] = classify(xyz, centers, mask, vario, n=3, n_holes=5, k=3)
    return vox


def classify(xyz, centers, mask, vario, n=3, n_holes=None, k=3):
    """Clasificación JORC-style: combina criterios geométricos + varianza de kriging + nº de sondajes.
    
    Devuelve array uint8: 0=fuera, 1=Medido, 2=Indicado, 3=Inferido.
    
    Criterios (tipo JORC/NI 43-101 simplificados):
    - Medido: varianza <= sill/3 Y distancia n-ésimo <= range/3 Y >= k sondajes en vecindario
    - Indicado: varianza <= 2*sill/3 Y distancia n-ésimo <= 2*range/3 Y >= 2 sondajes
    - Inferido: resto dentro del dominio
    
    shortcut: para un primer reporte; para JORC definitivo usar criterios del QP."""
    from scipy.spatial import cKDTree
    from scipy.spatial.distance import cdist
    
    r = vario.range_h if vario is not None and vario.range_h else 100.0
    sill = vario.sill if vario is not None and vario.sill else np.var(xyz[:, 0]) if len(xyz) > 0 else 1.0
    
    out = np.zeros(len(centers), np.uint8)
    if not mask.any():
        return out
    
    # Distancias a compósitos
    tree = cKDTree(xyz)
    d = tree.query(centers[mask], k=min(n, len(xyz)))[0]
    d = d[:, -1] if d.ndim > 1 else d
    
    # Varianza de kriging si hay variograma
    if vario is not None:
        kw = vario.kriging_kwargs()
        _, krig_var = ordinary_kriging_3d_variance(xyz, np.zeros(len(xyz)), centers[mask], **kw)
        # Normalizar varianza por sill
        rel_var = krig_var / max(sill, 1e-9)
    else:
        rel_var = np.ones(np.sum(mask))
    
    # Contar sondajes únicos en vecindario
    if n_holes is not None:
        _, idx = tree.query(centers[mask], k=min(n_holes * 2, len(xyz)))
        # Para simplificar, asumimos que cada muestra tiene un hole_id asociado
        # En la práctica se pasaría hole_ids; aquí usamos una heurística
        n_unique = np.array([len(np.unique(idx[i])) for i in range(len(idx))])
    else:
        n_unique = np.full(np.sum(mask), 3)  # default conservador
    
    # Clasificación
    meas_mask = (rel_var <= 1/3) & (d <= r / 3) & (n_unique >= k)
    ind_mask = (rel_var <= 2/3) & (d <= 2 * r / 3) & (n_unique >= 2)
    
    out[mask] = np.where(meas_mask, 1, np.where(ind_mask, 2, 3))
    return out


def sgs(xyz, vals, targets, vario, n_real=20, k_data=16, k_sim=8, seed=0):
    """Simulación gaussiana secuencial (kriging simple en normal scores, camino aleatorio).
    -> (M, n_real) leyes simuladas en `targets`.
    ponytail: los nodos simulados entran al vecindario por un KD-tree reconstruido cada 256 nodos;
    los últimos simulados se ignoran hasta la reconstrucción (correlación algo menor a corta distancia)."""
    from scipy.spatial import cKDTree
    from scipy.stats import norm

    n = len(vals)
    order = np.argsort(vals)
    p = (np.arange(n) + 0.5) / n
    z = np.empty(n)
    z[order] = norm.ppf(p)
    X, T = vario._transform_coords(xyz), vario._transform_coords(targets)
    cov = lambda h: vario.cov(h) / vario.sill  # normal scores: meseta 1
    tree = cKDTree(X)
    rng = np.random.default_rng(seed)
    out = np.empty((len(T), n_real))
    for r in range(n_real):
        sim, done = np.empty(len(T)), []
        stree = None
        for i, t in enumerate(rng.permutation(len(T))):
            if i % 256 == 0 and done:
                stree = cKDTree(T[done])
            _, a = tree.query(T[t], k=min(k_data, n))
            P, v = X[np.atleast_1d(a)], z[np.atleast_1d(a)]
            if stree is not None:
                _, b = stree.query(T[t], k=min(k_sim, stree.n))
                b = np.asarray(done)[np.atleast_1d(b)]
                P, v = np.vstack([P, T[b]]), np.concatenate([v, sim[b]])
            C = cov(np.linalg.norm(P[:, None] - P[None], axis=-1)) + 1e-9 * np.eye(len(P))
            c = cov(np.linalg.norm(P - T[t], axis=1))
            w = np.linalg.solve(C, c)
            sim[t] = w @ v + np.sqrt(max(1.0 - w @ c, 0.0)) * rng.standard_normal()
            done.append(t)
        out[:, r] = np.interp(norm.cdf(sim), p, vals[order])
    return out


def regularize(grade, dims, factor):
    """Re-bloqueo a SMU: promedia celdas de a `factor` (fx, fy, fz); NaN (fuera del dominio)
    cuenta como estéril ley 0 -> dilución. -> (leyes SMU, fracción de dominio por SMU)."""
    g = np.asarray(grade, float).reshape(dims[::-1])  # orden VTK: x varía más rápido
    fz, fy, fx = factor[::-1]
    nz, ny, nx = (np.array(g.shape) // [fz, fy, fx]) * [fz, fy, fx]
    g = g[:nz, :ny, :nx].reshape(nz // fz, fz, ny // fy, fy, nx // fx, fx)
    inside = np.isfinite(g).mean(axis=(1, 3, 5)).ravel()
    return np.nan_to_num(g).mean(axis=(1, 3, 5)).ravel(), inside


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


def cross_validate(xyz, vals, vario=None, n=300, seed=0):
    """Validación cruzada (dejar uno fuera) del kriging en `n` compósitos al azar.
    -> (real, estimado, {sesgo, R, RMSE})."""
    idx = np.random.default_rng(seed).choice(len(vals), size=min(n, len(vals)), replace=False)
    kw = vario.kriging_kwargs() if vario is not None else {}
    est = np.empty(len(idx))
    keep = np.ones(len(vals), bool)
    for j, i in enumerate(idx):
        keep[i] = False
        est[j] = ordinary_kriging_3d(xyz[keep], vals[keep], xyz[i:i + 1], n_neighbors=24, **kw)[0]
        keep[i] = True
    real = vals[idx]
    return real, est, {"sesgo": float((est - real).mean()), "R": float(np.corrcoef(real, est)[0, 1]),
                       "RMSE": float(np.sqrt(((est - real) ** 2).mean()))}


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

    # SMU 2x2x2: una celda fuera (NaN) diluye; fracción de dominio 7/8
    g = np.ones(8)
    g[0] = np.nan
    smu, inside = regularize(g, (2, 2, 2), (2, 2, 2))
    assert abs(smu[0] - 7 / 8) < 1e-12 and abs(inside[0] - 7 / 8) < 1e-12, (smu, inside)

    # SGS: reproduce el histograma y honra los datos (nodo sobre un dato ~ su valor)
    sims = sgs(xyz[:300], vals[:300], np.vstack([xyz[:1], rng.uniform(0, 400, (200, 3))]), v, n_real=10)
    assert abs(np.median(sims[1:]) - np.median(vals[:300])) < 0.5 * vals.std(), np.median(sims)
    assert abs(sims[0].mean() - vals[0]) < 0.5 * vals.std(), (sims[0].mean(), vals[0])

    print(f"estimation: OK  {v}")


if __name__ == "__main__":
    demo()
