"""Punto de entrada: python -m geoform [proyecto.geoform | collars.csv surveys.csv intervals.csv]
                         [--screenshot out.png] [--section] [--smoke-gui] [--report]

Sin argumentos abre la GUI con el proyecto demo (pórfido Cu sintético).
--screenshot renderiza headless; --smoke-gui construye la GUI, calcula y sale (test).
"""
import argparse
import os

from .project import Project, demo_project


def main(argv=None):
    ap = argparse.ArgumentParser(prog="geoform", description="Modelador geológico 3D")
    ap.add_argument("files", nargs="*", help="proyecto .geoform, o collars surveys intervals (CSV)")
    ap.add_argument("--assays", help="CSV de leyes (modo CSV)")
    ap.add_argument("--topo", help="DEM .asc (modo CSV)")
    ap.add_argument("--screenshot", help="render headless a PNG")
    ap.add_argument("--section", action="store_true", help="corte N-S por el centro (con --screenshot)")
    ap.add_argument("--report", action="store_true", help="imprime volúmenes y ley-tonelaje")
    ap.add_argument("--smoke-gui", action="store_true", help="construir la GUI, calcular y salir")
    args = ap.parse_args(argv)

    if not args.files:
        project = demo_project()
    elif len(args.files) == 1:
        project = Project.open(args.files[0])
    elif len(args.files) == 3:
        c, s, i = (os.path.abspath(f) for f in args.files)
        project = Project(None, name=os.path.basename(os.path.dirname(c)), collars=c, surveys=s, intervals=i,
                          assays=args.assays and os.path.abspath(args.assays),
                          topography=args.topo and os.path.abspath(args.topo))
    else:
        ap.error("pasa un .geoform o los 3 CSV (collars surveys intervals)")

    if args.screenshot or args.report:
        project.load().build()
        print(project.report())
        if args.screenshot:
            from .scene import plot_project

            clip = None
            if args.section:
                ys = [c[1] for c in project.collars.values()]
                clip = ((0, 1, 0), (0, (min(ys) + max(ys)) / 2, 0))
            plot_project(project, screenshot=args.screenshot, clip=clip, view=(20, 22) if clip else None)
            print(f"captura: {args.screenshot}")
        return

    from .gui import run

    win = run(project, smoke=args.smoke_gui)
    if args.smoke_gui:
        print(f"GUI OK  capas: {len(win.layer_defs)}, visibles: {len(win.actors)}")


if __name__ == "__main__":
    main()
