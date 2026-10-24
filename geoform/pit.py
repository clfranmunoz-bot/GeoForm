"""Optimización de rajo (pit final, equivalente a Lerchs-Grossmann / Whittle).

El pit óptimo es la clausura de valor máximo del modelo de bloques: un bloque solo se extrae
si salen también los bloques sobre él dentro del cono de talud. Se resuelve exacto como corte
mínimo (Picard 1976) con el flujo máximo de scipy:
  fuente -> bloque de valor > 0 (capacidad = valor), bloque de valor < 0 -> sumidero (= -valor),
  bloque -> cada bloque que lo cubre (capacidad infinita).
Los bloques alcanzables desde la fuente en el grafo residual forman el pit.

Valor de bloque ($): t * max(ley·rec·precio - costo_planta, 0) - t * costo_mina.
Talud: con bloques cúbicos, los 9 bloques del banco superior (3x3) dan ~45°; con bloque de
altura h y lado a, el ángulo efectivo es atan(h / a).
"""
import numpy as np

DEFAULTS = {"price": 8500.0, "recovery": 0.88, "mine_cost": 2.5, "proc_cost": 14.0, "block": 20.0}


def block_values(project, P, block, cfg):
    """Valor ($) y ley de bloques con centros P (coords. motor); aire = NaN."""
    m = project.model
    lab = m.label_at(P)
    grade = np.zeros(len(P))
    b = project.blocks
    if b is not None:  # ley del block model de kriging (vecino más cercano)
        ijk = np.floor((P - np.array(b.origin)) / np.array(b.spacing)).astype(int)
        dims = np.array(b.dimensions) - 1
        ok = np.all((ijk >= 0) & (ijk < dims), axis=1)
        idx = ijk[ok, 0] + dims[0] * (ijk[ok, 1] + dims[1] * ijk[ok, 2])
        g = np.asarray(b.cell_data["grade"])[idx]
        grade[np.where(ok)[0]] = np.nan_to_num(g)
    dens = np.array([project.density(u) for u in m.units] + [0.0])[lab]  # lab -1 -> aire
    t = dens * block ** 3
    k = 0.01 if project.cfg["unit"] == "%" else 1e-6  # % -> fracción; g/t -> t/t
    proc = grade * k * cfg["recovery"] * cfg["price"] - cfg["proc_cost"]
    value = t * (np.maximum(proc, 0) - cfg["mine_cost"])
    value[lab < 0] = np.nan
    return value, grade, t, proc > 0


def optimize(project, cfg=None):
    """-> pv.ImageData (celdas de `block` m) con cell_data 'pit' (0/1), 'value', 'grade', 'ore'
    y un resumen {t_mineral, ley, t_esteril, razon, valor}."""
    import pyvista as pv
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order, maximum_flow

    cfg = {**DEFAULTS, **(cfg or {})}
    a = cfg["block"]
    lo, hi = np.array(project.model.grid.bounds).reshape(3, 2).T
    dims = np.maximum(np.round((hi - lo) / a).astype(int), 1)
    vox = pv.ImageData(dimensions=dims + 1, spacing=[a] * 3, origin=lo)
    P = np.asarray(vox.cell_centers().points)
    value, grade, tons, ore = block_values(project, P, a, cfg)
    nx, ny, nz = dims
    solid = ~np.isnan(value)
    ids = -np.ones(len(P), int)
    ids[solid] = np.arange(solid.sum())
    n = int(solid.sum())
    S, T = n, n + 1
    scale = 1.0 / 100.0  # $ -> enteros (maximum_flow pide capacidades int32)
    v = np.round(np.nan_to_num(value[solid]) * scale).astype(np.int64)
    rows, cols, caps = [], [], []
    pos, neg = np.where(v > 0)[0], np.where(v < 0)[0]
    rows += [np.full(len(pos), S), neg]
    cols += [pos, np.full(len(neg), T)]
    caps += [v[pos], -v[neg]]
    BIG = int(min(np.abs(v).sum() + 1, 2 ** 31 - 1))
    I, J, K = np.unravel_index(np.arange(len(P)), (nx, ny, nz), order="F")
    for di in (-1, 0, 1):  # precedencia: bloque -> 3x3 del banco de arriba (z motor - 1 = más alto)
        for dj in (-1, 0, 1):
            i2, j2, k2 = I + di, J + dj, K - 1
            ok = solid & (i2 >= 0) & (i2 < nx) & (j2 >= 0) & (j2 < ny) & (k2 >= 0)
            up = np.where(ok)[0]
            tgt = ids[i2[up] + nx * (j2[up] + ny * k2[up])]
            keep = tgt >= 0  # sobre el aire no hay que sacar nada
            rows.append(ids[up][keep])
            cols.append(tgt[keep])
            caps.append(np.full(keep.sum(), BIG))
    r, c, cap = (np.concatenate(x).astype(np.int32) for x in (rows, cols, [np.asarray(q, np.int64) for q in caps]))
    G = coo_matrix((cap.astype(np.int32), (r, c)), shape=(n + 2, n + 2)).tocsr()
    G.sum_duplicates()
    flow = maximum_flow(G, S, T).flow
    res = (G - flow).tocsr()  # capacidad residual directa
    res = res + (flow.T.tocsr())  # y la inversa (flujo que se puede devolver)
    res.data[res.data < 0] = 0
    res.eliminate_zeros()
    reach = breadth_first_order(res, S, directed=True, return_predecessors=False)
    in_pit = np.zeros(n + 2, bool)
    in_pit[reach] = True
    pit = np.zeros(len(P), np.uint8)
    pit[solid] = in_pit[:n]
    vox.cell_data["pit"] = pit
    vox.cell_data["value"] = np.nan_to_num(value)
    vox.cell_data["grade"] = grade
    vox.cell_data["ore"] = (ore & (pit == 1)).astype(np.uint8)
    mo, mw = (pit == 1) & ore, (pit == 1) & ~ore
    t_ore, t_w = float(tons[mo].sum()), float(tons[mw].sum())
    summary = {"t_mineral": t_ore, "ley": float((grade[mo] * tons[mo]).sum() / t_ore) if t_ore else 0.0,
               "t_esteril": t_w, "razon": t_w / t_ore if t_ore else 0.0,
               "valor": float(np.nan_to_num(value)[pit == 1].sum())}
    return vox, summary


def pit_shell(vox):
    """Superficie del pit (isosuperficie del indicador) en coords. motor."""
    pts = vox.cell_data_to_point_data()
    m = pts.contour([0.5], scalars="pit")
    return m.smooth_taubin(n_iter=30) if m.n_points else m


def demo():
    from .project import demo_project

    p = demo_project().load()
    p.log = lambda *_: None
    p.build()
    vox, s = optimize(p)
    pit = vox.cell_data["pit"].astype(bool)
    assert s["valor"] > 0 and s["t_mineral"] > 0, s
    # talud: todo bloque del pit tiene su 3x3 superior en el pit (o es aire / borde)
    nx, ny, nz = np.array(vox.dimensions) - 1
    P3 = pit.reshape((nx, ny, nz), order="F")
    air = np.isnan(np.where(vox.cell_data["value"] == 0, np.nan, 1.0)).reshape((nx, ny, nz), order="F")
    bad = 0
    for i, j, k in zip(*np.nonzero(P3[1:-1, 1:-1, 1:])):
        blk = P3[i:i + 3, j:j + 3, k] | air[i:i + 3, j:j + 3, k]
        bad += not blk.all()
    assert bad == 0, f"{bad} bloques violan el talud"
    print(f"pit: OK  mineral {s['t_mineral'] / 1e6:.1f} Mt a {s['ley']:.2f}%, estéril {s['t_esteril'] / 1e6:.1f} Mt "
          f"(razón {s['razon']:.2f}), valor US$ {s['valor'] / 1e6:,.0f} M")


if __name__ == "__main__":
    demo()
