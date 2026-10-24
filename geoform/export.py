"""Exportación: mallas a DXF (3DFACE, sin dependencias) / OBJ, block model a CSV y reporte."""
import csv
import os

import numpy as np

from .scene import flip


def write_dxf(mesh, path, layer="GEOFORM"):
    """Malla triangulada -> DXF ASCII con entidades 3DFACE (lo leen AutoCAD, Vulcan, Datamine...)."""
    tri = mesh.extract_surface(algorithm="dataset_surface").triangulate()
    pts = np.asarray(tri.points)
    faces = tri.faces.reshape(-1, 4)[:, 1:]
    layer = layer.replace(":", "_")
    with open(path, "w") as fh:
        fh.write("0\nSECTION\n2\nENTITIES\n")
        for a, b, c in faces:
            fh.write(f"0\n3DFACE\n8\n{layer}\n")
            for k, i in enumerate((a, b, c, c)):  # 4ª esquina = 3ª (triángulo)
                x, y, z = pts[i]
                fh.write(f"1{k}\n{x:.3f}\n2{k}\n{y:.3f}\n3{k}\n{z:.3f}\n")
        fh.write("0\nENDSEC\n0\nEOF\n")
    return path


def write_block_csv(project, path):
    """Block model: centro (X, Y, Elev), tamaño, litología y ley estimada."""
    b = project.blocks
    centers = np.asarray(b.cell_centers().points)
    grade = b.cell_data["grade"]
    lith = project.model.label_at(centers)
    sx, sy, sz = project.cfg["block"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["X", "Y", "Z", "DX", "DY", "DZ", "LITO", project.cfg["element"], "DENSIDAD"])
        for (x, y, z), k, g in zip(centers, lith, grade):
            if k < 0 or not np.isfinite(g):
                continue
            u = project.units[k]
            w.writerow([f"{x:.2f}", f"{y:.2f}", f"{-z:.2f}", sx, sy, sz, u, f"{g:.4f}", project.density(u)])
    return path


def export_all(project, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    out = []
    m = project.model
    for u in project.units:
        mesh = flip(m.solid_mesh(u))
        out.append(write_dxf(mesh, os.path.join(out_dir, f"{u}.dxf"), u))
        mesh.save(os.path.join(out_dir, f"{u}.obj"))
        out.append(os.path.join(out_dir, f"{u}.obj"))
    for i, f in enumerate(project.cfg["faults"]):
        out.append(write_dxf(flip(m.fault_mesh(i)), os.path.join(out_dir, f"{f['name']}.dxf"), f["name"]))
    if project.blocks is not None:
        out.append(write_block_csv(project, os.path.join(out_dir, "block_model.csv")))
    path = os.path.join(out_dir, "reporte.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(project.report())
    out.append(path)
    return out


def demo():
    import tempfile

    import pyvista as pv

    with tempfile.TemporaryDirectory() as tmp:
        p = write_dxf(pv.Cube(), os.path.join(tmp, "c.dxf"))
        txt = open(p).read()
        assert txt.count("3DFACE") == 12 and txt.endswith("EOF\n"), txt.count("3DFACE")
    print("export: OK  DXF 3DFACE (cubo = 12 triángulos)")


if __name__ == "__main__":
    demo()
