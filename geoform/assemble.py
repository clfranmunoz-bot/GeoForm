"""Ensamblaje del modelo geológico por clasificación de vóxeles (motor simple).

Cada unidad tiene una superficie (techo) con campo implícito F>0 debajo.
Un vóxel pertenece a la unidad más somera cuyo techo queda por encima.
El modelador completo (fallas, intrusivos, topografía) está en geomodel.py.
"""
import numpy as np

from .model import build_surface, contact_points_from_intervals, make_surface_field


def layer_fields(collars, surveys, intervals, units, side="top"):
    """RBF del TECHO de cada unidad, en orden `units` (somero -> profundo)."""
    fields = []
    for u in units:
        c, t = contact_points_from_intervals(collars, surveys, intervals, u, side)
        fields.append((u, make_surface_field(c, t)))
    return fields


def surface_meshes(collars, surveys, intervals, units, side="top"):
    """Mallas (verts, tris) del techo de cada unidad. [(name, verts, tris)]."""
    out = []
    for u in units:
        c, t = contact_points_from_intervals(collars, surveys, intervals, u, side)
        verts, tris = build_surface(c, t)
        out.append((u, verts, tris))
    return out


def classify(centers, fields):
    """Etiqueta cada centro con el índice de su unidad en `fields`; -1 = aire."""
    centers = np.asarray(centers, float)
    n = len(fields)
    below = np.stack([f(centers) > 0 for _, f in fields], axis=0)  # (n, M)
    labels = np.full(len(centers), -1, int)
    assigned = np.zeros(len(centers), bool)
    for k in range(n):
        mask = below[k] if k == n - 1 else (below[k] & ~below[k + 1])
        mask &= ~assigned
        labels[mask] = k
        assigned |= mask
    return labels


def block_volume(labels, voxel):
    """Volumen por unidad. labels (M,), voxel = volumen de un vóxel."""
    uniq, counts = np.unique(labels, return_counts=True)
    return {int(u): int(c) * voxel for u, c in zip(uniq, counts) if u >= 0}


def demo():
    # pozos verticales 5x5; tres unidades de TECHO PLANO en z=20 y z=50, piso 200
    collars, surveys, intervals = {}, {}, {}
    for x in np.linspace(0, 40, 5):
        for y in np.linspace(0, 40, 5):
            hid = f"H{x:.0f}_{y:.0f}"
            collars[hid] = (x, y, 0.0, 0.0, -90.0)
            surveys[hid] = [(0, 0, -90), (200, 0, -90)]
            intervals[hid] = [(0.0, 20.0, "Overburden"), (20.0, 50.0, "Andesita"), (50.0, 200.0, "Basement")]

    units = ["Overburden", "Andesita", "Basement"]
    fields = layer_fields(collars, surveys, intervals, units)

    probes = np.array([[20, 20, 10], [20, 20, 35], [20, 20, 120]])
    labels = classify(probes, fields)
    assert labels.tolist() == [0, 1, 2], labels

    cx = np.arange(5, 40, 10)
    cz = np.arange(5, 200, 10)
    gx, gy, gz = np.meshgrid(cx, cx, cz, indexing="ij")
    centers = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    vol = block_volume(classify(centers, fields), 10 * 10 * 10)
    expect = {0: 32000, 1: 48000, 2: 240000}
    for k, v in expect.items():
        assert abs(vol[k] - v) / v < 1e-6, (k, vol[k], v)

    print(f"assemble: OK  volúmenes {{0: {vol[0]}, 1: {vol[1]}, 2: {vol[2]}}}")


def classify_constraints(centers, units):
    """Clasificador general (erosión/inconformidad). units = [(name, below, above)].

    below/above = listas de campos rbf; la unidad existe donde TODOS los
    'below' son >0 (punto bajo esa superficie) y TODOS los 'above' son <0
    (sobre esa superficie). Gana la primera unidad que cumple (más joven).
    """
    centers = np.asarray(centers, float)
    labels = np.full(len(centers), -1, int)
    for k, (_name, below, above) in enumerate(units):
        ok = np.ones(len(centers), bool)
        for f in below:
            ok &= f(centers) > 0
        for f in above:
            ok &= f(centers) < 0
        labels[ok & (labels == -1)] = k
    return labels


def demo_erosion():
    """Basamento inclinado truncado por una superficie de erosión plana."""
    def plane_field(a, b, c):  # superficie z = a + b*x + c*y -> F>0 debajo
        return lambda pts: pts[:, 2] - (a + b * pts[:, 0] + c * pts[:, 1])

    f_base = plane_field(90, -0.8, 0)
    f_ero = plane_field(80, 0, 0)
    units = [
        ("Joven", [], [f_ero]),
        ("Basamento", [f_base, f_ero], []),
    ]
    probes = np.array([[20, 0, 30], [20, 0, 77], [20, 0, 85]])
    labels = classify_constraints(probes, units)
    assert labels.tolist() == [0, 0, 1], labels
    print("erosion: OK  pinch-out correcto (basamento truncado contra la erosion)")


if __name__ == "__main__":
    demo()
    demo_erosion()
