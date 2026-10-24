"""Estimación de leyes: IDW + kriging ordinario 3D (vecindad móvil, sin pykrige).

# shortcut: kriging local O(M·k³) con k~16-24 vecinos; suficiente para un block
# model interactivo. Para millones de bloques, vectorizar por lotes o paralelizar.
"""
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


def ordinary_kriging_3d(xyz, values, targets, range_=None, n_neighbors=16, nugget=None, sill=None, aniso=(1.0, 1.0, 1.0)):
    """Kriging ordinario 3D local (vecindad móvil) con variograma esférico.

    Para cada target resuelve el sistema OK con sus k vecinos más cercanos.
    range_ = alcance mayor del variograma; None -> 0.4 * extensión de los datos.
    nugget/sill: modelo ajustado (None -> 5% / varianza). aniso = alcances relativos
    (x, y, z) respecto de range_: se reescalan las coordenadas -> variograma isótropo."""
    from scipy.linalg import solve
    from scipy.spatial import cKDTree
    from scipy.spatial.distance import cdist

    a = np.asarray(aniso, float)
    xyz = np.asarray(xyz, float) / a
    values = np.asarray(values, float)
    targets = np.asarray(targets, float) / a
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
        h = np.asarray(h, float)
        c = np.zeros_like(h)
        m = (h > 0) & (h < r)
        c[m] = (S - nug) * (1 - 1.5 * (h[m] / r) + 0.5 * (h[m] / r) ** 3)
        c[h == 0] = S
        return c

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
