"""Leyes: compositado downhole y puntos 3D de assays para el block model."""
import numpy as np

from .model import _point_at_depth, hole_path


def composite(froms, tos, values, interval):
    """Composita intervalos de ley a malla regular (promedio ponderado por longitud).

    froms/tos/values: arrays de un sondaje. interval: longitud objetivo.
    Devuelve (comp_from, comp_to, comp_values); sin muestra -> NaN.
    """
    froms = np.asarray(froms, float)
    tos = np.asarray(tos, float)
    values = np.asarray(values, float)
    out_from, out_to, out_val = [], [], []
    comp = froms.min()
    end = tos.max()
    while comp < end:
        lo = np.maximum(froms, comp)
        hi = np.minimum(tos, comp + interval)
        length = np.maximum(0.0, hi - lo)
        v = (values * length).sum() / length.sum() if length.sum() > 0 else np.nan
        out_from.append(comp)
        out_to.append(comp + interval)
        out_val.append(v)
        comp += interval
    return np.array(out_from), np.array(out_to), np.array(out_val)


def assay_points_3d(collars, surveys, assays):
    """Puntos 3D (punto medio desurveyado) de cada assay. -> (xyz (N,3), values (N,)).

    assays: {hole_id: [(from_depth, to_depth, value), ...]}.
    """
    xyz, vals = [], []
    for hid, rows in assays.items():
        x, y, z, az, dip = collars[hid]
        mds, pts = hole_path(x, y, z, az, dip, surveys.get(hid, []))
        for f, t, v in rows:
            p0 = _point_at_depth(mds, pts, f)
            p1 = _point_at_depth(mds, pts, t)
            xyz.append((p0 + p1) / 2.0)
            vals.append(v)
    return np.asarray(xyz), np.asarray(vals)


def demo():
    # compositado: [0,5]=2 y [5,10]=4 -> composito de 10m = 3
    f, t, v = composite([0, 5], [5, 10], [2.0, 4.0], 10.0)
    assert len(v) == 1 and abs(v[0] - 3.0) < 1e-9, v
    # composito de 5m preserva las muestras
    f, t, v = composite([0, 5], [5, 10], [2.0, 4.0], 5.0)
    assert np.allclose(v, [2.0, 4.0]), v
    # hueco sin muestra -> NaN (composito [4,6] no toca ninguna muestra)
    f, t, v = composite([0, 6], [4, 10], [2.0, 4.0], 2.0)
    assert np.isnan(v[2]), v
    # puntos 3D: pozo vertical, assay [0,10] -> punto medio en profundidad 5
    collars = {"H": (0.0, 0.0, 0.0, 0.0, -90.0)}
    surveys = {"H": [(0, 0, -90), (100, 0, -90)]}
    xyz, vals = assay_points_3d(collars, surveys, {"H": [(0.0, 10.0, 2.5)]})
    assert abs(xyz[0, 2] - 5.0) < 1e-9 and vals[0] == 2.5, (xyz, vals)
    print("grade: OK  compositado + puntos 3D de assays")


if __name__ == "__main__":
    demo()
