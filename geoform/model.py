"""Superficie geológica desde sondajes: desurvey + contactos + RBF + malla.

Pipeline completo: DB -> desurvey -> puntos de contacto -> RBF -> marching cubes.
Construcción de superficies implícitas desde sondajes.
"""
import numpy as np

from .desurvey import desurvey
from .implicit import build_mesh, field_from_rbf, make_rbf


def hole_path(x, y, z, az, dip, surveys):
    """Desurvey + collar en md=0. Devuelve (mds, pts)."""
    pts = desurvey(x, y, z, az, dip, [(s[0], s[1], s[2]) for s in surveys])
    mds = [0.0] + [s[0] for s in surveys]
    return np.asarray(mds, float), np.asarray(pts, float)


def _point_at_depth(mds, pts, depth):
    """Interpola linealmente la posición 3D a una profundidad medida."""
    if depth <= mds[0]:
        return pts[0]
    if depth >= mds[-1]:
        return pts[-1]
    i = int(np.searchsorted(mds, depth)) - 1
    t = (depth - mds[i]) / (mds[i + 1] - mds[i])
    return pts[i] + t * (pts[i + 1] - pts[i])


def _tangent_at(mds, pts, depth):
    """Vector unitario tangente al sondaje en una profundidad (sentido abajo)."""
    i = int(np.searchsorted(mds, depth))
    if i <= 0:
        seg = pts[1] - pts[0]
    elif i >= len(mds):
        seg = pts[-1] - pts[-2]
    else:
        seg = pts[i] - pts[i - 1]
    n = np.linalg.norm(seg)
    return seg / n if n > 0 else np.array([0.0, 0.0, 1.0])


def contact_points_from_intervals(collars, surveys, intervals, target, side="top"):
    """Puntos de contacto + tangentes para una litología `target`.

    collars:  {hole_id: (x, y, z, az, dip)}
    surveys:  {hole_id: [(md, az, dip), ...]}
    intervals:{hole_id: [(from, to, lithology), ...]}
    side: 'top' (techo) | 'base' (muro).
    Devuelve (contacts (N,3), tangents (N,3)).
    """
    contacts, tangents = [], []
    for hid, ints in intervals.items():
        x, y, z, az, dip = collars[hid]
        mds, pts = hole_path(x, y, z, az, dip, surveys.get(hid, []))
        for f, t, lith in ints:
            if lith != target:
                continue
            d = f if side == "top" else t
            contacts.append(_point_at_depth(mds, pts, d))
            tangents.append(_tangent_at(mds, pts, d))
    return np.asarray(contacts), np.asarray(tangents)


def _off_points(contacts, tangents, offset):
    """Off-points ±offset a lo largo del sondaje, con su valor (±offset)."""
    up = contacts + offset * tangents
    down = contacts - offset * tangents
    return np.column_stack([
        np.vstack([up, down]),
        np.concatenate([np.full(len(contacts), offset),
                        np.full(len(contacts), -offset)]),
    ])


def _field_gradient_dirs(rbf, pts, h=1e-3):
    """Dirección del gradiente del campo en cada punto (aproximación a la normal)."""
    pts = np.asarray(pts, float)
    g = np.empty_like(pts)
    for d in range(3):
        delta = np.zeros_like(pts)
        delta[:, d] = h
        g[:, d] = (rbf(pts + delta) - rbf(pts - delta)) / (2.0 * h)
    n = np.linalg.norm(g, axis=1, keepdims=True)
    return g / np.where(n < 1e-12, 1.0, n)


def make_surface_field(contacts, tangents, polarity_offset=5.0, refine=2, neighbors=None):
    """RBF de la superficie. Refina los off-points hacia la normal del campo:
    el sondaje no es perpendicular a la superficie en general, y el valor de
    los off-points debe ser la distancia a lo largo de la normal para que el
    campo sea consistente (firma de distancia). neighbors = k activa RBF local.
    """
    contacts = np.asarray(contacts, float)
    direction = np.asarray(tangents, float)
    rbf = make_rbf(contacts, _off_points(contacts, direction, polarity_offset), neighbors)
    for _ in range(refine):
        direction = _field_gradient_dirs(rbf, contacts)
        rbf = make_rbf(contacts, _off_points(contacts, direction, polarity_offset), neighbors)
    return rbf


def build_surface(contacts, tangents, polarity_offset=5.0, neighbors=None):
    """Superficie implícita. Devuelve (verts, tris)."""
    contacts = np.asarray(contacts, float)
    tangents = np.asarray(tangents, float)
    rbf = make_surface_field(contacts, tangents, polarity_offset, neighbors=neighbors)
    xs, ys, zs, vals = field_from_rbf(rbf, contacts)
    return build_mesh(xs, ys, zs, vals)


def demo():
    # 5x5 pozos verticales; techo de "Andesita" = plano z = 50 + 0.5x + 0.3y
    collars, surveys, intervals = {}, {}, {}
    for x in np.linspace(0, 40, 5):
        for y in np.linspace(0, 40, 5):
            hid = f"H{x:.0f}_{y:.0f}"
            d = 50 + 0.5 * x + 0.3 * y
            collars[hid] = (x, y, 0.0, 0.0, -90.0)
            surveys[hid] = [(0, 0, -90), (200, 0, -90)]
            intervals[hid] = [(0.0, d, "Overburden"), (d, 200.0, "Andesita")]

    contacts, tangents = contact_points_from_intervals(
        collars, surveys, intervals, "Andesita", side="top"
    )
    verts, tris = build_surface(contacts, tangents)
    assert len(verts) > 0 and len(tris) > 0, "malla vacía"

    resid = verts[:, 2] - (50 + 0.5 * verts[:, 0] + 0.3 * verts[:, 1])
    assert np.abs(resid).max() < 5.0, np.abs(resid).max()
    print(f"model: OK  techo Andesita {len(verts)} vértices, residuo máx {np.abs(resid).max():.3f}")
    demo_inclined()


def demo_inclined():
    """Pozos inclinados (azimut/dip variables) cruzando un plano conocido."""
    def plane_z(x, y):
        return 50 + 0.5 * x + 0.3 * y

    collars, surveys, intervals = {}, {}, {}
    k = 0
    for x in np.linspace(0, 40, 6):
        for y in np.linspace(0, 40, 6):
            az = [0, 45, 90, 135, 180, 225, 270, 315][k % 8]
            dip = [-55, -65, -75, -85][k % 4]
            inc = np.radians(90 + dip)
            azr = np.radians(az)
            tx, ty, tz = np.sin(inc) * np.sin(azr), np.sin(inc) * np.cos(azr), np.cos(inc)
            denom = tz - 0.5 * tx - 0.3 * ty
            if abs(denom) < 1e-6:
                k += 1
                continue
            d = plane_z(x, y) / denom
            if not (5 < d < 180):
                k += 1
                continue
            hid = f"HI{x:.0f}_{y:.0f}"
            collars[hid] = (x, y, 0.0, az, dip)
            surveys[hid] = [(0, az, dip), (200, az, dip)]
            intervals[hid] = [(0.0, d, "Overburden"), (d, 200.0, "Andesita")]
            k += 1

    contacts, tangents = contact_points_from_intervals(collars, surveys, intervals, "Andesita", "top")
    verts, _ = build_surface(contacts, tangents)
    resid = verts[:, 2] - plane_z(verts[:, 0], verts[:, 1])
    assert np.abs(resid).max() < 0.5, np.abs(resid).max()
    print(f"model: OK  pozos inclinados, {len(contacts)} contactos, residuo máx {np.abs(resid).max():.3f}")


if __name__ == "__main__":
    demo()
