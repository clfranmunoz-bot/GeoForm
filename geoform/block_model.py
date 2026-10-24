"""Block model 3D: estimación de leyes sobre grilla regular (IDW o kriging ordinario 3D)."""
import numpy as np

from .kriging import idw, ordinary_kriging_3d


def grid_centers(bounds, nx, ny, nz):
    """Centros de vóxeles de una grilla regular. bounds = (x0,x1,y0,y1,z0,z1)."""
    x0, x1, y0, y1, z0, z1 = bounds
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    zs = np.linspace(z0, z1, nz)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()]), (xs, ys, zs)


def block_model(xyz, values, bounds, nx=20, ny=20, nz=20, power=2, n_neighbors=8, method="idw"):
    """Estimación en grilla 3D. method='idw'|'kriging'. Devuelve (estimados (M,), (xs, ys, zs))."""
    centers, (xs, ys, zs) = grid_centers(bounds, nx, ny, nz)
    if method == "kriging":
        try:
            est = ordinary_kriging_3d(xyz, values, centers)
        except Exception:  # fallback robusto: IDW si el sistema OK es singular
            est = idw(xyz, values, centers, power=power, n_neighbors=n_neighbors)
    else:
        est = idw(xyz, values, centers, power=power, n_neighbors=n_neighbors)
    return est, (xs, ys, zs)


def demo():
    rng = np.random.default_rng(0)

    # campo constante -> estimación exacta
    xyz = rng.uniform(0, 100, (300, 3))
    est, (xs, ys, zs) = block_model(xyz, np.full(300, 3.0), (0, 100, 0, 100, 0, 100))
    assert est.shape == (20 * 20 * 20,), est.shape
    assert np.allclose(est, 3.0, atol=1e-9), est

    print(f"block_model: OK  grilla {len(xs)}x{len(ys)}x{len(zs)} = {len(est)} bloques")


if __name__ == "__main__":
    demo()
