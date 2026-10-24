"""Yacimiento sintético realista para el demo: topografía, estratigrafía plegada,
falla normal y pórfido cuprífero intrusivo. Genera los CSV + DEM + ortofoto de geoform/data.

Convención de los datos: collar z = ELEVACIÓN (msnm). El motor trabaja en
profundidad (z_motor = -elevación); load_project hace la conversión.
"""
import csv
import os

import numpy as np

X0, Y0, SIZE = 1000.0, 2000.0, 600.0

# falla normal: rumbo N30E, manteo 70° al SE, salto 50 m (bloque colgante baja)
FAULT = {"name": "Falla Principal", "point": [1330.0, 2280.0, 400.0], "dip_direction": 120.0, "dip": 70.0}
THROW = 50.0
STRAT = ["Cobertura", "Volcanico", "Sedimentario", "Basamento"]
INTRUSION = "Porfido"


def topo_elev(x, y):
    u, v = (x - X0) / SIZE, (y - Y0) / SIZE
    return (480 + 45 * np.sin(2.2 * u + 0.5) * np.cos(1.7 * v) + 30 * np.exp(-((u - .7) ** 2 + (v - .3) ** 2) / .04)
            - 25 * np.exp(-((u - .25) ** 2 + (v - .75) ** 2) / .03) + 8 * np.sin(9 * u) * np.sin(7 * v))


def fault_side(x, y, z):
    """>0 en el bloque colgante (sobre el plano de falla). z = elevación."""
    dd, dip = np.radians(FAULT["dip_direction"]), np.radians(FAULT["dip"])
    n = np.array([np.sin(dd) * np.sin(dip), np.cos(dd) * np.sin(dip), np.cos(dip)])
    px, py, pz = FAULT["point"]
    return n[0] * (x - px) + n[1] * (y - py) + n[2] * (z - pz)


def _contacts(x, y):
    """Elevación de la base de cobertura y los techos de Sedimentario y Basamento."""
    u, v = (x - X0) / SIZE, (y - Y0) / SIZE
    fold = 35 * np.sin(2 * np.pi * (0.8 * u + 0.3 * v)) + 15 * v
    base_cob = topo_elev(x, y) - (18 + 10 * np.sin(5 * u + 3 * v))
    return base_cob, 360 + fold, 250 + 0.8 * fold - 20 * u


def porphyry(x, y, z):
    """>0 dentro del stock (elipsoide inclinado con lóbulos)."""
    dx, dy, dz = (x - 1290) / 150, (y - 2290) / 120, (z - 270 - 0.25 * (x - 1290)) / 210
    lobes = 0.12 * np.sin(3 * np.arctan2(dy, dx)) * np.cos(2 * dz)
    return 1 + lobes - (dx ** 2 + dy ** 2 + dz ** 2)


def lithology(x, y, z):
    if porphyry(x, y, z) > 0 and z < _contacts(x, y)[0]:
        return INTRUSION
    zz = z + THROW if fault_side(x, y, z) > 0 else z  # bloque colgante desplazado
    cob, vol, sed = _contacts(x, y)
    if z > cob:
        return "Cobertura"
    if zz > vol:
        return "Volcanico"
    if zz > sed:
        return "Sedimentario"
    return "Basamento"


def cu_grade(x, y, z, lith, rng):
    r2 = ((x - 1300) / 170) ** 2 + ((y - 2290) / 140) ** 2 + ((z - 300) / 200) ** 2
    if lith == INTRUSION:
        g = 0.35 + 1.4 * np.exp(-r2) + 0.25 * np.sin(z / 25 + x / 40)
    elif lith == "Cobertura":
        g = 0.01
    else:
        g = 0.05 + 0.5 * np.exp(-r2 * 1.8)
    return max(0.005, g * rng.lognormal(0, 0.25))


def _hole_points(x, y, z, az, dip, depth, step):
    inc, a = np.radians(90 + dip), np.radians(az)
    d = np.array([np.sin(inc) * np.sin(a), np.sin(inc) * np.cos(a), -np.cos(inc)])
    md = np.arange(0, depth + 1e-9, step)
    return md, np.array([x, y, z]) + md[:, None] * d


def generate(out_dir, seed=7, spacing=60.0):
    rng = np.random.default_rng(seed)
    collars, surveys, intervals, assays = [], [], [], []
    grid = [(gx, gy) for gx in np.arange(X0 + 30, X0 + SIZE, spacing) for gy in np.arange(Y0 + 30, Y0 + SIZE, spacing)]
    infill = [(gx, gy) for gx in np.arange(1180, 1420, 40.0) for gy in np.arange(2190, 2400, 40.0)]  # relleno sobre el pórfido
    for k, (gx, gy) in enumerate(grid + infill):
        x, y = gx + rng.uniform(-12, 12), gy + rng.uniform(-12, 12)
        z = float(topo_elev(x, y))
        az, dip = (float(rng.choice([0, 60, 120, 180, 240, 300])), float(rng.uniform(-80, -60))) if k % 3 else (0.0, -90.0)
        depth = float(round(rng.uniform(380, 480)))
        hid = f"DDH-{k:03d}"
        collars.append([hid, round(x, 2), round(y, 2), round(z, 2), depth, az, dip])
        surveys += [[hid, 0, az, dip], [hid, depth, az, dip]]
        md, pts = _hole_points(x, y, z, az, dip, depth, 2.0)
        liths = [lithology(*p) for p in pts]
        start = 0
        for i in range(1, len(md) + 1):
            if i == len(md) or liths[i] != liths[start]:
                end = md[i] if i < len(md) else depth
                if end > md[start]:  # el último paso puede caer justo en el fondo del pozo
                    intervals.append([hid, float(md[start]), float(end), liths[start]])
                start = i
        for f in np.arange(0, depth, 5.0):
            t = min(f + 5.0, depth)
            j = min(int((f + t) / 4), len(pts) - 1)  # índice del punto medio (paso 2 m)
            assays.append([hid, f, t, "Cu", round(cu_grade(*pts[j], liths[j], rng), 3)])

    os.makedirs(out_dir, exist_ok=True)
    _w(os.path.join(out_dir, "collars.csv"), ["hole_id", "x", "y", "z", "max_depth", "azimuth", "dip"], collars)
    _w(os.path.join(out_dir, "surveys.csv"), ["hole_id", "depth", "azimuth", "dip"], surveys)
    _w(os.path.join(out_dir, "intervals.csv"), ["hole_id", "from_depth", "to_depth", "lithology"], intervals)
    _w(os.path.join(out_dir, "assays.csv"), ["hole_id", "from_depth", "to_depth", "element", "value"], assays)
    write_dem(os.path.join(out_dir, "terrain.asc"))
    write_satellite(os.path.join(out_dir, "satellite.png"))
    return len(collars)


def write_dem(path, cell=10.0, pad=100.0):
    n = int((SIZE + 2 * pad) / cell) + 1
    xs = X0 - pad + cell * np.arange(n)
    ys = Y0 - pad + cell * np.arange(n)
    with open(path, "w") as fh:
        fh.write(f"ncols {n}\nnrows {n}\nxllcorner {xs[0]}\nyllcorner {ys[0]}\ncellsize {cell}\nNODATA_value -9999\n")
        for y in ys[::-1]:  # fila 0 = norte
            fh.write(" ".join(f"{topo_elev(x, y):.2f}" for x in xs) + "\n")


def write_satellite(path, n=800, pad=100.0):
    """Ortofoto sintética coherente con el DEM: sombreado + vegetación en quebradas +
    roca/suelo en lomas + caminos de acceso."""
    from PIL import Image

    v = np.linspace(Y0 + SIZE + pad, Y0 - pad, n)  # fila 0 = norte
    u = np.linspace(X0 - pad, X0 + SIZE + pad, n)
    X, Y = np.meshgrid(u, v)
    Z = topo_elev(X, Y)
    gy, gx = np.gradient(Z, v[1] - v[0], u[1] - u[0])
    shade = np.clip(0.75 + 0.9 * (-gx * 0.6 + gy * 0.5) / np.hypot(1, np.hypot(gx, gy)), 0.35, 1.25)
    rng = np.random.default_rng(1)
    noise = Image.fromarray((rng.random((n // 8, n // 8)) * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)
    noise = np.asarray(noise, float) / 255
    t = np.clip((Z - Z.min()) / np.ptp(Z), 0, 1)
    veg = np.clip(1.2 - 1.6 * t + 0.5 * (noise - 0.5), 0, 1)
    rock = np.array([168, 140, 108]) * (0.85 + 0.3 * noise[..., None])
    green = np.array([74, 104, 52]) * (0.8 + 0.4 * noise[..., None])
    img = rock * (1 - veg[..., None]) + green * veg[..., None]
    road = np.abs(Y - (2300 + 120 * np.sin((X - 1000) / 140))) < 4
    road |= np.abs(X - (1150 + 0.4 * (Y - 2000))) < 3
    img[road] = [205, 190, 160]
    img *= shade[..., None]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path)


def _w(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    print(f"synth: OK  {generate(out)} sondajes en {out}")
