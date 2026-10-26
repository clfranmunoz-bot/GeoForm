"""Superficie implícita por RBF (thin-plate spline) + marching cubes.

Puntos de contacto (valor 0) + puntos de polaridad (±) alimentan un RBF;
la isosuperficie en 0 es la malla geológica.

# shortcut: RBF global O(N^2); para >100k puntos, usar neighbors (RBF local).
"""
import numpy as np
from scipy.interpolate import RBFInterpolator


def make_rbf(contact_points, off_points, neighbors=None):
    """RBF callable f(pts)->valores: 0 en contactos, ± en off-points.

    neighbors=k activa el RBF local (solo los k contactos más cercanos por
    punto) -> O(M*k) en vez de O(M*N); None = global exacto. Usar neighbors
    para datasets grandes (miles de contactos).
    """
    pts = np.vstack([contact_points, off_points[:, :3]])
    vals = np.concatenate([np.zeros(len(contact_points)), off_points[:, 3]])
    return RBFInterpolator(
        pts, vals, kernel="thin_plate_spline", smoothing=0.0, neighbors=neighbors
    )


def field_from_rbf(rbf, pts, resolution=60, pad=0.15):
    """Evalúa un rbf en una grilla regular que cubre `pts`. -> (xs, ys, zs, values)."""
    extent = pts.max(axis=0) - pts.min(axis=0) + 1e-9
    lo = pts.min(axis=0) - pad * extent
    hi = pts.max(axis=0) + pad * extent
    xs = np.linspace(lo[0], hi[0], resolution)
    ys = np.linspace(lo[1], hi[1], resolution)
    zs = np.linspace(lo[2], hi[2], resolution)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    q = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    values = rbf(q).reshape(gx.shape)
    return xs, ys, zs, values


def build_field(contact_points, off_points, resolution=60, pad=0.15):
    """(compat) campo escalar en grilla regular desde contactos + off-points."""
    pts = np.vstack([contact_points, off_points[:, :3]])
    rbf = make_rbf(contact_points, off_points)
    return field_from_rbf(rbf, pts, resolution, pad)


def build_mesh(xs, ys, zs, values, level=0.0):
    """Extrae la isosuperficie con marching cubes (pyvista). Devuelve (verts, tris)."""
    import pyvista as pv

    grid = pv.ImageData(
        dimensions=(len(xs), len(ys), len(zs)),
        spacing=(xs[1] - xs[0], ys[1] - ys[0], zs[1] - zs[0]),
        origin=(xs[0], ys[0], zs[0]),
    )
    grid.point_data["values"] = values.ravel(order="F")  # ImageData usa orden Fortran
    mesh = grid.contour([level])
    tris = mesh.faces.reshape(-1, 4)[:, 1:] if mesh.n_cells else np.empty((0, 3), int)
    return np.asarray(mesh.points), tris


def _sphere_dataset(n=80, seed=0):
    """Puntos de una esfera unitaria centrada en el origen + polaridad."""
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    on = d                                        # |x| = 1, valor 0
    off = np.column_stack([
        np.vstack([d * 1.4, d * 0.6]),            # afuera / adentro
        np.concatenate([np.full(n, 0.4), np.full(n, -0.4)]),
    ])
    return on, off


def demo():
    on, off = _sphere_dataset()
    xs, ys, zs, vals = build_field(on, off)
    verts, tris = build_mesh(xs, ys, zs, vals)
    assert len(verts) > 0 and len(tris) > 0, "malla vacía"
    r = np.linalg.norm(verts, axis=1)
    assert r.min() > 0.7 and r.max() < 1.3, (r.min(), r.max())
    print(f"implicit: OK  esfera ~{len(verts)} vértices, r in [{r.min():.2f}, {r.max():.2f}]")


if __name__ == "__main__":
    demo()
