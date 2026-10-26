"""Exportación: mallas a DXF (3DFACE, sin dependencias) / OBJ / STL / PLY, block model a CSV y reporte.
Formatos adicionales: GOCAD TSurf, VTK, Parquet, CSV mejorado."""
import csv
import os
import json

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


def write_tsurf(mesh, path, name="GEOFORM"):
    """Malla -> GOCAD TSurf (formato ASCII, lo leen Leapfrog, Surpac, Datamine, Micromine)."""
    tri = mesh.extract_surface(algorithm="dataset_surface").triangulate()
    pts = np.asarray(tri.points)
    faces = tri.faces.reshape(-1, 4)[:, 1:]
    
    with open(path, "w") as fh:
        fh.write("GOCAD TSurf 1\n")
        fh.write(f"HEADER {{\n  name:{name}\n}}\n")
        fh.write("TFACE\n")
        fh.write(f"VRTX {len(pts)}\n")
        for i, (x, y, z) in enumerate(pts):
            fh.write(f"{i+1} {x:.6f} {y:.6f} {z:.6f}\n")
        fh.write(f"TRGL {len(faces)}\n")
        for i, (a, b, c) in enumerate(faces):
            fh.write(f"{i+1} {a+1} {b+1} {c+1}\n")
        fh.write("END\n")
    return path


def write_vtk(mesh, path):
    """Malla -> VTK (legacy ASCII), legible por ParaView, VisIt, Leapfrog, etc."""
    tri = mesh.extract_surface(algorithm="dataset_surface").triangulate()
    tri.save(path)
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


def write_block_parquet(project, path):
    """Block model -> Parquet (columnar, eficiente, con metadatos)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("pyarrow requerido: pip install pyarrow")
    
    b = project.blocks
    centers = np.asarray(b.cell_centers().points)
    grade = b.cell_data["grade"]
    domain = b.cell_data.get("domain", np.zeros(len(centers), dtype=bool))
    cls = b.cell_data.get("class", np.zeros(len(centers), dtype=np.uint8))
    lith = project.model.label_at(centers)
    sx, sy, sz = project.cfg["block"]
    
    # Filtrar solo bloques dentro del dominio
    mask = (lith >= 0) & np.isfinite(grade) & (domain > 0)
    
    table = pa.table({
        "X": centers[mask, 0],
        "Y": centers[mask, 1],
        "Z": -centers[mask, 2],  # elevación
        "DX": np.full(mask.sum(), sx),
        "DY": np.full(mask.sum(), sy),
        "DZ": np.full(mask.sum(), sz),
        "LITO": [project.units[k] for k in lith[mask]],
        project.cfg["element"]: grade[mask],
        "CLASS": cls[mask],  # 1=Medido, 2=Indicado, 3=Inferido
        "DENSIDAD": [project.density(project.units[k]) for k in lith[mask]],
    })
    
    # Metadatos del proyecto
    metadata = {
        "project_name": project.cfg["name"],
        "element": project.cfg["element"],
        "unit": project.cfg["unit"],
        "cell_size": project.cfg["cell"],
        "block_size": project.cfg["block"],
        "date": str(np.datetime64('now')),
    }
    table = table.replace_schema_metadata({b"geoform": json.dumps(metadata).encode()})
    
    pq.write_table(table, path)
    return path


def write_block_vtk(project, path):
    """Block model -> VTK ImageData (structured grid) para visualización 3D."""
    import pyvista as pv
    b = project.blocks
    # El bloque ya es un ImageData, solo guardamos
    b.save(path)
    return path


def export_all(project, out_dir, formats=("dxf", "obj", "stl", "ply", "tsurf", "csv", "parquet", "vtk")):
    """Exporta todo en múltiples formatos.
    formats: subconjunto de ('dxf', 'obj', 'stl', 'ply', 'tsurf', 'csv', 'parquet', 'vtk')"""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    m = project.model
    
    for u in project.units:
        mesh = flip(m.solid_mesh(u))
        if "dxf" in formats:
            out.append(write_dxf(mesh, os.path.join(out_dir, f"{u}.dxf"), u))
        for ext in ("obj", "stl", "ply"):  # pyvista elige el escritor por la extensión
            if ext in formats:
                p = os.path.join(out_dir, f"{u}.{ext}")
                mesh.extract_surface(algorithm="dataset_surface").triangulate().save(p)
                out.append(p)
        if "tsurf" in formats:
            out.append(write_tsurf(mesh, os.path.join(out_dir, f"{u}.ts"), u))
        if "vtk" in formats:
            out.append(write_vtk(mesh, os.path.join(out_dir, f"{u}.vtk")))
    
    for i, f in enumerate(project.cfg["faults"]):
        fault_mesh = flip(m.fault_mesh(i))
        if "dxf" in formats:
            out.append(write_dxf(fault_mesh, os.path.join(out_dir, f"{f['name']}.dxf"), f["name"]))
        if "tsurf" in formats:
            out.append(write_tsurf(fault_mesh, os.path.join(out_dir, f"{f['name']}.ts"), f["name"]))
        if "vtk" in formats:
            out.append(write_vtk(fault_mesh, os.path.join(out_dir, f"{f['name']}.vtk")))
    
    if project.blocks is not None:
        if "csv" in formats:
            out.append(write_block_csv(project, os.path.join(out_dir, "block_model.csv")))
        if "parquet" in formats:
            try:
                out.append(write_block_parquet(project, os.path.join(out_dir, "block_model.parquet")))
            except ImportError:  # pyarrow es opcional (pip install geoform[parquet])
                pass
        if "vtk" in formats:
            out.append(write_block_vtk(project, os.path.join(out_dir, "block_model.vtk")))
    
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
        for ext in ("stl", "ply"):
            q = os.path.join(tmp, f"c.{ext}")
            pv.Cube().triangulate().save(q)
            assert pv.read(q).n_cells == 12, ext
    print("export: OK  DXF 3DFACE (cubo = 12 triángulos)")


if __name__ == "__main__":
    demo()
