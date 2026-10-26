"""Estimación de leyes: IDW + kriging ordinario 3D (vecindad móvil, sin pykrige).

# shortcut: kriging local O(M·k³) con k~16-24 vecinos; suficiente para un block
# model interactivo. Para millones de bloques, vectorizar por lotes o paralelizar.
Soporta anisotropía 3D completa: rotation_matrix + aniso_ratios (major, semi-major, minor)."""
import numpy as np


def idw(xyz, values, targets, power=2, n_neighbors=8):
    """IDW 3D. xyz:(N,3) muestras, values:(N,), targets:(M,3) -> (M,) estimados."""
    xyz = np.asarray(xyz, float)
    values = np.asarray(values, float)
    targets = np.asarray(targets, float)
    out = np.empty(len(targets))
    for i, p in enumerate(targets):
        d = np.linalg.norm(xyz - p, axis=1)
        idx = np.argpartition(d, min(n_neighbors, len(d) - 1))[:n_neighbors]
        dd = d[idx]
        dd = np.where(dd < 1e-12, 1e-12, dd)
        w = 1.0 / dd ** power
        out[i] = (w * values[idx]).sum() / w.sum()
    return out


def _transform_aniso(xyz, rotation_matrix=None, aniso_ratios=None):
    """Transforma coordenadas a espacio isótropo usando anisotropía 3D completa."""
    if rotation_matrix is not None:
        xyz = xyz @ rotation_matrix.T
    if aniso_ratios is not None:
        xyz = xyz / np.asarray(aniso_ratios, float)
    return xyz


def _cov_model(h, model_type, nugget, sill, range_):
    """Covarianza para diferentes modelos de variograma."""
    h = np.asarray(h, float)
    c = np.zeros_like(h)
    
    if model_type == "exponential":
        # C(h) = sill - nugget * (h>0) - sill * (1 - exp(-3h/range))
        c = sill - nugget * (h > 0) - sill * (1 - np.exp(-3 * h / range_))
    elif model_type == "gaussian":
        # C(h) = sill - nugget * (h>0) - sill * (1 - exp(-3(h/range)^2))
        c = sill - nugget * (h > 0) - sill * (1 - np.exp(-3 * (h / range_)**2))
    elif model_type == "hole_effect":
        # Efecto hoyo: esférico + oscilación
        r = np.clip(h / range_, 0, 1)
        spherical_part = np.where((h > 0) & (h < range_), 1.5 * r - 0.5 * r**3, 0)
        osc = 0.1 * np.sin(2 * np.pi * h / range_) * np.exp(-h / range_)
        c = sill - nugget * (h > 0) - sill * (spherical_part + osc)
    else:  # spherical
        m = (h > 0) & (h < range_)
        c[m] = (sill - nugget) * (1 - 1.5 * (h[m] / range_) + 0.5 * (h[m] / range_) ** 2)
    c[h == 0] = sill
    return c


def ordinary_kriging_3d(xyz, values, targets, range_=None, n_neighbors=16, nugget=None, sill=None, 
                        aniso=(1.0, 1.0, 1.0), model_type="spherical", 
                        rotation_matrix=None, aniso_ratios=None):
    """Kriging ordinario 3D local (vecindad móvil) con variograma configurable.
    
    Para cada target resuelve el sistema OK con sus k vecinos más cercanos.
    range_ = alcance mayor del variograma; None -> 0.4 * extensión de los datos.
    nugget/sill: modelo ajustado (None -> 5% / varianza). 
    aniso = alcances relativos (x, y, z) respecto de range_ (compatibilidad legacy).
    model_type: "spherical", "exponential", "gaussian", "hole_effect"
    rotation_matrix: matriz 3x3 de rotación (anisotropía 3D completa)
    aniso_ratios: (major, semi-major, minor) ratios de anisotropía"""
    from scipy.linalg import solve
    from scipy.spatial import cKDTree
    from scipy.spatial.distance import cdist

    # Transformar a espacio anisotrópico
    a = np.asarray(aniso, float)
    xyz = _transform_aniso(np.asarray(xyz, float), rotation_matrix, aniso_ratios) / a
    values = np.asarray(values, float)
    targets = _transform_aniso(np.asarray(targets, float), rotation_matrix, aniso_ratios) / a
    n = len(xyz)
    if n < 4:
        return idw(xyz, values, targets)
    S = float(np.var(values)) if sill is None else float(sill)
    if np.var(values) < 1e-12:  # campo constante: kriging degenera, devolver la media
        return np.full(len(targets), values.mean())
    r = range_ if range_ is not None else 0.4 * float(np.ptp(xyz, axis=0).max())
    if r <= 0:
        return idw(xyz, values, targets)
    nug = 0.05 * S if nugget is None else float(nugget)

    def cov(h):
        return _cov_model(h, model_type, nug, S, r)

    tree = cKDTree(xyz)
    out = np.empty(len(targets))
    k = min(n_neighbors, n)
    for i, p in enumerate(targets):
        dist, idx = tree.query(p, k=k)
        idx = np.atleast_1d(idx)
        dist = np.atleast_1d(dist)
        m = len(idx)
        K = np.empty((m + 1, m + 1))
        K[:m, :m] = cov(cdist(xyz[idx], xyz[idx]))
        K[:m, m] = 1.0
        K[m, :m] = 1.0
        K[m, m] = 0.0
        b = np.empty(m + 1)
        b[:m] = cov(dist)
        b[m] = 1.0
        w = solve(K, b)
        out[i] = float(w[:m] @ values[idx])
    return out


def ordinary_kriging_3d_variance(xyz, values, targets, range_=None, n_neighbors=16, nugget=None, sill=None, 
                                 aniso=(1.0, 1.0, 1.0), model_type="spherical",
                                 rotation_matrix=None, aniso_ratios=None):
    """Kriging ordinario 3D con varianza de estimación (varianza de kriging).
    
    Returns: (estimates, variances) - ambos arrays de forma (M,).
    La varianza de kriging = varianza del error de estimación = C(0) - w^T * C - lagrange.
    Para kriging ordinario: sigma2_K = S - w^T * c - mu, donde mu es el multiplicador de Lagrange.
    Soporta anisotropía 3D completa y modelos de variograma configurables."""
    from scipy.linalg import solve
    from scipy.spatial import cKDTree
    from scipy.spatial.distance import cdist

    # Transformar a espacio anisotrópico
    a = np.asarray(aniso, float)
    xyz = _transform_aniso(np.asarray(xyz, float), rotation_matrix, aniso_ratios) / a
    values = np.asarray(values, float)
    targets = _transform_aniso(np.asarray(targets, float), rotation_matrix, aniso_ratios) / a
    n = len(xyz)
    if n < 4:
        est = idw(xyz, values, targets)
        return est, np.full(len(targets), np.var(values))
    S = float(np.var(values)) if sill is None else float(sill)
    if np.var(values) < 1e-12:
        return np.full(len(targets), values.mean()), np.zeros(len(targets))
    r = range_ if range_ is not None else 0.4 * float(np.ptp(xyz, axis=0).max())
    if r <= 0:
        est = idw(xyz, values, targets)
        return est, np.full(len(targets), S)
    nug = 0.05 * S if nugget is None else float(nugget)

    def cov(h):
        return _cov_model(h, model_type, nug, S, r)

    tree = cKDTree(xyz)
    out = np.empty(len(targets))
    var_out = np.empty(len(targets))
    k = min(n_neighbors, n)
    for i, p in enumerate(targets):
        dist, idx = tree.query(p, k=k)
        idx = np.atleast_1d(idx)
        dist = np.atleast_1d(dist)
        m = len(idx)
        K = np.empty((m + 1, m + 1))
        K[:m, :m] = cov(cdist(xyz[idx], xyz[idx]))
        K[:m, m] = 1.0
        K[m, :m] = 1.0
        K[m, m] = 0.0
        b = np.empty(m + 1)
        b[:m] = cov(dist)
        b[m] = 1.0
        w = solve(K, b)
        est = float(w[:m] @ values[idx])
        out[i] = est
        # Kriging variance: sigma2_K = C(0) - w^T * c - mu
        # where C(0) = S, c = cov(dist), mu = w[m] (Lagrange multiplier)
        sigma2 = S - float(w[:m] @ cov(dist)) - w[m]
        # Ensure non-negative (numerical issues)
        var_out[i] = max(sigma2, 0.0)
    return out, var_out


def demo():
    rng = np.random.default_rng(1)

    # IDW campo constante -> devuelve la constante
    xyz = rng.uniform(0, 100, (200, 3))
    t = rng.uniform(0, 100, (10, 3))
    out = idw(xyz, np.full(200, 5.0), t)
    assert np.allclose(out, 5.0, atol=1e-9), out

    # IDW lineal: valor = 2x + 3y, estimado en una muestra debe ser exacto
    gx, gy = np.meshgrid(np.linspace(0, 10, 8), np.linspace(0, 10, 8), indexing="ij")
    pts = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
    vals = 2 * pts[:, 0] + 3 * pts[:, 1]
    est = idw(pts, vals, np.array([[5.0, 5.0, 0.0]]), n_neighbors=4)
    assert abs(est[0] - 25.0) < 0.5, est

    # kriging 3D: interpolador exacto en las muestras (campo no constante)
    pts3 = rng.uniform(0, 50, (60, 3))
    vals3 = 2 * pts3[:, 0] + 3 * pts3[:, 1] + pts3[:, 2]
    est3 = ordinary_kriging_3d(pts3, vals3, pts3[:5].copy(), n_neighbors=12)
    assert np.allclose(est3, vals3[:5], atol=0.5), (est3, vals3[:5])
    assert np.isfinite(est3).all()

    print("kriging: OK (IDW constante + lineal + kriging ordinario 3D local)")


if __name__ == "__main__":
    demo()