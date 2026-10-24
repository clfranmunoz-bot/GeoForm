"""Topografía desde DEM raster (ESRI ASCII .asc). Sin dependencias nuevas."""
import os

import numpy as np


def read_asc(path):
    """Lee un DEM ASCII (.asc): devuelve grillas X, Y (coordenadas) y Z (elevación)."""
    hdr, body = {}, []
    with open(path) as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 2 and parts[0][0].isalpha():
                hdr[parts[0].lower()] = float(parts[1])
            else:
                body.extend(float(p) for p in parts)
    ncols, nrows = int(hdr["ncols"]), int(hdr["nrows"])
    cell = hdr["cellsize"]
    z = np.array(body).reshape(nrows, ncols)  # fila 0 = norte, col 0 = oeste
    nodata = hdr.get("nodata_value")
    if nodata is not None:
        z = np.where(np.isclose(z, nodata), np.nan, z)
    x = hdr["xllcorner"] + cell * np.arange(ncols)                 # oeste -> este
    y = hdr["yllcorner"] + cell * (nrows - 1 - np.arange(nrows))   # norte -> sur
    X, Y = np.meshgrid(x, y, indexing="ij")
    return X, Y, z.T


def load_dem(path):
    """DEM -> (xs, ys, Z elev) con ejes crecientes, Z[i, j] en (xs[i], ys[j])."""
    X, Y, Z = read_asc(path)
    return X[:, 0], Y[0, ::-1], Z[:, ::-1]


def terrain_mesh(path):
    """Superficie de terreno en espacio de PROFUNDIDAD (z = -elevación)."""
    import pyvista as pv

    X, Y, Z = read_asc(path)
    return pv.StructuredGrid(X, Y, -Z).extract_surface(algorithm="dataset_surface")


def write_demo_dem(path, n=60, cell=1.0):
    """DEM sintético: colina gaussiana + pendiente suave (elevación ~0 de fondo)."""
    x = np.arange(n) * cell
    X, Y = np.meshgrid(x, x, indexing="ij")
    z = 50.0 * np.exp(-((X - 0.35 * n) ** 2 + (Y - 0.6 * n) ** 2) / (2 * 10.0 ** 2)) \
        + 0.10 * X - 0.05 * Y
    with open(path, "w") as fh:
        fh.write(f"ncols {n}\nnrows {n}\nxllcorner 0\nyllcorner 0\ncellsize {cell}\nNODATA_value -9999\n")
        for r in range(n):  # fila 0 = norte (y máximo)
            fh.write(" ".join(f"{v:.2f}" for v in z[:, n - 1 - r]) + "\n")


def texture_from_image(path):
    """Imagen (PNG/JPG) -> textura VTK vía PIL (sin imageio)."""
    import pyvista as pv
    from PIL import Image

    img = np.asarray(Image.open(path).convert("RGB"))
    return pv.Texture(img)


def demo():
    """Self-check: DEM sintético -> read_asc debe poner el pico en (x≈21, y≈36)."""
    import tempfile

    tmp = tempfile.mkdtemp()  # no pisar el DEM del proyecto demo en geoform/data
    path = os.path.join(tmp, "terrain.asc")
    write_demo_dem(path)
    X, Y, Z = read_asc(path)
    xs, ys, Zi = load_dem(path)
    assert np.all(np.diff(xs) > 0) and np.all(np.diff(ys) > 0) and np.nanmax(Zi) == np.nanmax(Z)
    i, j = np.unravel_index(np.nanargmax(Z), Z.shape)
    assert abs(X[i, j] - 0.35 * 60) < 2, (X[i, j], Y[i, j])
    assert abs(Y[i, j] - 0.6 * 60) < 2, (X[i, j], Y[i, j])
    assert np.nanmax(Z) > 40.0, np.nanmax(Z)
    print(f"topography: OK  DEM .asc -> grilla, pico en (x={X[i, j]:.0f}, y={Y[i, j]:.0f})")
    return path


if __name__ == "__main__":
    demo()
