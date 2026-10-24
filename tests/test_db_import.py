"""Schema SQLite + importadores CSV: carga correcta y rechazo de datos inválidos.

python -m tests.test_db_import
"""
import os
import tempfile

from geoform.db import create_db
from geoform.importers.csv_importer import (ImportError_, import_assays, import_collars, import_intervals,
                                            import_surveys)


def _w(dir_, name, text):
    p = os.path.join(dir_, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _raises(fn, *a):
    try:
        fn(*a)
    except ImportError_ as e:
        return str(e)
    raise AssertionError(f"{fn.__name__} debía rechazar los datos")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        conn = create_db(":memory:")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"collars", "surveys", "intervals", "assays"} <= tables, tables

        # encabezados en mayúsculas y con BOM: se aceptan
        c = _w(tmp, "c.csv", "﻿HOLE_ID,X,Y,Z,MAX_DEPTH,AZIMUTH,DIP\nH1,0,0,500,100,0,-90\nH2,10,0,505,,,\n")
        assert import_collars(conn, c) == 2
        assert conn.execute("SELECT dip FROM collars WHERE hole_id='H2'").fetchone()[0] is None
        s = _w(tmp, "s.csv", "hole_id,depth,azimuth,dip\nH1,0,0,-90\nH1,100,0,-90\n")
        assert import_surveys(conn, s) == 2
        i = _w(tmp, "i.csv", "hole_id,from_depth,to_depth,lithology\nH1,0,20,Grava\nH1,20,100,Andesita\n")
        assert import_intervals(conn, i) == 2
        a = _w(tmp, "a.csv", "hole_id,from_depth,to_depth,element,value\nH1,0,10,Cu,0.5\nH1,10,20,Cu,\n")
        assert import_assays(conn, a) == 2

        # validación en la frontera: columna faltante, texto en número, intervalo invertido
        assert "faltan columnas" in _raises(import_collars, conn, _w(tmp, "b1.csv", "hole_id,x,y\nH,0,0\n"))
        assert "no es numérico" in _raises(import_collars, conn, _w(tmp, "b2.csv", "hole_id,x,y,z\nH,a,0,0\n"))
        msg = _raises(import_intervals, conn, _w(tmp, "b3.csv", "hole_id,from_depth,to_depth,lithology\nH,5,5,X\n"))
        assert "b3.csv:2" in msg, msg
        conn.close()
    print("OK: schema + importadores CSV (carga y validación)")


if __name__ == "__main__":
    main()
