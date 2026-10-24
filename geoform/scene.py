"""Escena 3D a partir de un Project construido.

Cada capa es (key, grupo, etiqueta, builder); el builder devuelve los kwargs de
add_mesh. La GUI usa layers() para el árbol de proyecto; plot_project() hace el
render headless. Todo se dibuja en elevación (z motor = -elev -> flip).
"""
import numpy as np

from . import theme

PALETTE = ["#e9c46a", "#9b6dd6", "#4ea8de", "#e07a3f", "#ef4444", "#4ade80", "#2dd4bf", "#f472b6"]
GRADE_CMAP = "turbo"
DEFAULT_ON = ("solid:", "fault:", "holes:grade")  # capas visibles al abrir / render por defecto
SOLID = dict(smooth_shading=True, ambient=0.16, diffuse=0.88, specular=0.35, specular_power=28)
_ZFLIP = np.diag([1.0, 1.0, -1.0, 1.0])
LIGHT = True  # fondo claro (Leapfrog); la GUI lo alterna


def colors():
    return theme.SCENE_LIGHT if LIGHT else theme.SCENE_DARK


def sbar(title):
    """Leyenda de color sobria, a la derecha, en la paleta del tema."""
    return {"title": title + "\n", "vertical": True, "position_x": 0.91, "position_y": 0.22, "width": 0.028,
            "height": 0.56, "n_labels": 6, "fmt": "%.2f", "color": colors()["text"], "font_family": "arial",
            "title_font_size": 15, "label_font_size": 12, "shadow": False, "bold": False}


def flip(mesh):
    return mesh.transform(_ZFLIP, inplace=False)


def unit_color(project, unit):
    c = project.cfg.get("colors", {}).get(unit)
    if c or unit not in project.units:  # volúmenes del usuario: ámbar salvo color propio
        return c or "#fbbf24"
    return PALETTE[project.units.index(unit) % len(PALETTE)]


def grade_clim(project):
    v = np.concatenate([[r[2] for r in rows] for rows in project.assays.values()])
    return 0.0, float(np.percentile(v, 98))


# -- constructores de mallas -------------------------------------------------------------
def terrain(project):
    import pyvista as pv

    xs, ys, Z = project.dem
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    s = pv.StructuredGrid(X, Y, Z).extract_surface(algorithm="dataset_surface")
    s["Elevation"] = s.points[:, 2]
    return s


def holes_mesh(project, mode="lith", radius=2.5):
    """Todos los sondajes como un solo tubo con escalar por tramo ('lith' o 'grade')."""
    import pyvista as pv

    from .grade import composite
    from .model import _point_at_depth, hole_path

    pts, lines, vals = [], [], []
    for hid, ints in project.intervals.items():
        x, y, z, az, dip = project.collars[hid]
        mds, path = hole_path(x, y, z, az, dip, project.surveys.get(hid, []))
        if mode == "grade":
            rows = project.assays.get(hid) if project.assays else None
            if not rows:
                continue
            f, t, v = composite(*zip(*rows), 5.0)
            segs = [(a, b, g) for a, b, g in zip(f, t, v) if np.isfinite(g)]
        else:
            segs = [(a, b, project.units.index(l)) for a, b, l in ints if l in project.units]
        for a, b, val in segs:
            n0 = len(pts)
            pts += [_point_at_depth(mds, path, a), _point_at_depth(mds, path, b)]
            lines += [2, n0, n0 + 1]
            vals.append(val)
    poly = pv.PolyData(np.asarray(pts, float), lines=np.asarray(lines))
    poly.cell_data["value"] = np.asarray(vals, float)
    return flip(poly).tube(radius=radius, n_sides=10, capping=False)


def contact_points(project, unit):
    """Puntos de contacto (sondajes + trazos a mano) del techo de `unit`, en elevación."""
    import pyvista as pv

    from .geomodel import hole_samples

    below = set(project.strat[project.strat.index(unit):])
    pts, vals = hole_samples(project.collars, project.surveys, project.intervals,
                             lambda l: l in below, lambda l: l in project.strat)
    q = np.vstack([pts[vals == 0] * [1, 1, -1],
                   np.asarray(project.cfg["picks"].get(unit, []), float).reshape(-1, 3)])
    return pv.PolyData(q)


# -- capas ------------------------------------------------------------------------------
def layers(project):
    """[(key, grupo, etiqueta, builder)] según lo que haya en el proyecto."""
    from matplotlib.colors import ListedColormap

    out = []
    if project.dem is not None:
        def topo():
            t = terrain(project)
            if project.file("satellite"):
                from .topography import texture_from_image
                tex = texture_from_image(project.file("satellite"))
                t = t.texture_map_to_plane(inplace=False)
                return dict(mesh=t, texture=tex, opacity=0.95, smooth_shading=True)
            return dict(mesh=t, scalars="Elevation", cmap="gist_earth", smooth_shading=True,
                        scalar_bar_args=sbar("Elevación (m)"))
        out.append(("topo", "Topografía", "Topografía", topo))
        out.append(("topo:elev", "Topografía", "Topografía (elevación)", lambda: dict(
            mesh=terrain(project), scalars="Elevation", cmap="turbo", smooth_shading=True,
            scalar_bar_args=sbar("Elevación (m)"))))

        def contours():
            t = terrain(project)
            z = t["Elevation"]
            lines = t.contour(np.arange(np.floor(z.min() / 10) * 10, z.max(), 10.0), scalars="Elevation")
            if project.model is not None:  # solo sobre el modelo, no en el margen del DEM
                b = project.model.grid.bounds
                lines = lines.clip_box((b[0], b[1], b[2], b[3], -1e5, 1e5), invert=False)
            return dict(mesh=lines.translate((0, 0, 1.5), inplace=False), color="#0b1016", line_width=1.4, opacity=0.7)
        out.append(("topo:contours", "Topografía", "Curvas de nivel (10 m)", contours))

    cmap_lith = ListedColormap([unit_color(project, u) for u in project.units])
    out.append(("holes:lith", "Sondajes", "Litología", lambda: dict(
        mesh=holes_mesh(project, "lith"), scalars="value", cmap=cmap_lith,
        clim=(-0.5, len(project.units) - 0.5), show_scalar_bar=False)))
    if project.assays:
        el = f"{project.cfg['element']} ({project.cfg['unit']})"
        out.append(("holes:grade", "Sondajes", f"Ley {el}", lambda: dict(
            mesh=holes_mesh(project, "grade", radius=1.6), scalars="value", cmap=GRADE_CMAP, clim=grade_clim(project),
            scalar_bar_args=sbar(el))))

    m = project.model
    if m is not None:
        for u in project.units:
            out.append((f"solid:{u}", "Volúmenes de salida", u, lambda u=u: dict(
                mesh=flip(m.solid_mesh(u)), color=unit_color(project, u), **SOLID)))
        for n in m.surfaces:
            if n != "Topografía":
                u = n.split(" ", 1)[1]
                out.append((f"surface:{n}", "Cronología de superficies", n, lambda n=n, u=u: dict(
                    mesh=flip(m.surface_mesh(n)), color=unit_color(project, u), opacity=0.6, **SOLID)))
                out.append((f"points:{n}", "Cronología de superficies", f"Contactos {u}", lambda u=u: dict(
                    mesh=contact_points(project, u), color=unit_color(project, u), point_size=6,
                    render_points_as_spheres=True)))
        for v in m.custom:
            out.append((f"volume:{v}", "Volúmenes de salida", v, lambda v=v: dict(
                mesh=flip(m.solid_mesh(v)), color=unit_color(project, v), **SOLID)))
        for i, f in enumerate(project.cfg["faults"]):
            out.append((f"fault:{i}", "Sistema de fallas", f["name"], lambda i=i: dict(
                mesh=flip(m.fault_mesh(i)), color="#f43f5e", opacity=0.55, smooth_shading=True)))

    if project.comp is not None:
        def comps():
            import pyvista as pv
            xyz, vals = project.comp
            pc = pv.PolyData(xyz * [1, 1, -1])
            pc["grade"] = vals
            return dict(mesh=pc, scalars="grade", cmap=GRADE_CMAP, clim=grade_clim(project),
                        point_size=7, render_points_as_spheres=True, show_scalar_bar=False)
        out.append(("composites", "Compósitos", f"Compósitos {project.cfg['domain']}", comps))
    if project.blocks is not None:
        def blocks():
            b = project.blocks.threshold(0.5, scalars="domain")
            return dict(mesh=flip(b), scalars="grade", cmap=GRADE_CMAP, clim=grade_clim(project),
                        show_edges=True, edge_color="#0d1117", line_width=0.4, show_scalar_bar=False)
        out.append(("blocks", "Modelos de bloques", f"Kriging {project.cfg['element']} en {project.cfg['domain']}", blocks))
    return out


def section(kw, normal, origin):
    """Aplica un corte (slicer) a los kwargs de una capa (malla abierta; la cara la pinta section_faces)."""
    mesh = kw["mesh"]
    return {**kw, "mesh": mesh.clip(normal=normal, origin=origin)} if mesh.n_points else kw


def section_faces(project, normal, origin):
    """Cara de corte coloreada por unidad (tapa del slicer): slice de cada sólido.
    -> [(unidad, malla)] en elevación."""
    m = project.model
    g = flip(m.grid)
    out = []
    for u in project.units:
        g.point_data["s"] = m.solids[u]
        sl = g.slice(normal=normal, origin=origin)
        if sl.n_points:
            sl = sl.clip_scalar(scalars="s", value=0.0, invert=False)
        if sl.n_points:
            out.append((u, sl))
    return out


def set_view(plotter, project, azimuth=225.0, elevation=30.0, zoom=1.0):
    """Cámara mirando al centro del modelo desde (azimut, altura) en grados."""
    b = np.array(plotter.bounds).reshape(3, 2)
    c = b.mean(axis=1)
    r = np.linalg.norm(b[:, 1] - b[:, 0]) * 2.0 / zoom
    a, e = np.radians(azimuth), np.radians(elevation)
    plotter.camera.focal_point = c
    plotter.camera.position = c + r * np.array([np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), np.sin(e)])
    plotter.camera.up = (0, 0, 1)


def decorate(plotter, project, zscale=1.0):
    c = colors()
    plotter.set_background(c["bg"][0], top=c["bg"][1])
    b = list(plotter.bounds)
    b[4], b[5] = b[4] / zscale, b[5] / zscale  # etiquetas en cotas reales con exageración vertical
    plotter.show_grid(xtitle="East (X)", ytitle="North (Y)", ztitle="Elev (Z)", color=c["grid"],
                      font_family="arial", font_size=10, fmt="%.0f", n_xlabels=5, n_ylabels=5, n_zlabels=4,
                      axes_ranges=b)
    plotter.add_axes(color=c["text"], line_width=2)
    plotter.enable_anti_aliasing("ssaa")


def plot_project(project, keys=None, screenshot=None, clip=None, view=None, size=(1600, 1000), opacity=None, zscale=1.0):
    """Render de las capas `keys` (None = DEFAULT_ON). clip = (normal, origin) en elevación;
    view = (azimut, altura[, zoom])."""
    import pyvista as pv

    p = pv.Plotter(off_screen=screenshot is not None, window_size=size)
    for key, _g, _label, build in layers(project):
        if (key not in keys) if keys is not None else not key.startswith(DEFAULT_ON):
            continue
        kw = build()
        if opacity and key in opacity:
            kw["opacity"] = opacity[key]
        if clip and not key.startswith("topo"):
            kw = section(kw, *clip)
        mesh = kw.pop("mesh")
        if mesh.n_points:
            p.add_mesh(mesh, name=key, **kw)
    if clip and project.model is not None:
        for u, face in section_faces(project, *clip):
            if (f"solid:{u}" in keys) if keys is not None else True:
                p.add_mesh(face, color=unit_color(project, u), name=f"cut:{u}", ambient=0.25)
    p.set_scale(zscale=zscale)
    decorate(p, project, zscale)
    set_view(p, project, *(view or (225.0, 30.0)))
    if screenshot:
        p.screenshot(screenshot)
        p.close()
        return screenshot
    p.show()
