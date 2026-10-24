"""Carga de datos de sondajes (CSV -> SQLite en memoria -> estructuras del motor).

Convención: los CSV traen la cota del collar en elevación; el motor trabaja en
profundidad (z = -elevación). La escena 3D está en geoform.scene y la GUI en geoform.gui.
"""
import os

import numpy as np

from .db import create_db
from .importers.csv_importer import import_assays, import_collars, import_intervals, import_surveys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_project(collars_csv, surveys_csv, intervals_csv):
    """CSVs -> (collars, surveys, intervals, units) en la estructura del modelador."""
    conn = create_db(":memory:")
    import_collars(conn, collars_csv)
    import_surveys(conn, surveys_csv)
    import_intervals(conn, intervals_csv)

    collars = {  # CSV z = elevación; motor z = profundidad = -elevación
        r[0]: (r[1], r[2], -r[3],
               r[4] if r[4] is not None else 0.0,
               r[5] if r[5] is not None else -90.0)
        for r in conn.execute("SELECT hole_id,x,y,z,azimuth,dip FROM collars")
    }
    surveys = {}
    for r in conn.execute("SELECT hole_id,depth,azimuth,dip FROM surveys ORDER BY depth"):
        hid, d, az, dip = r
        surveys.setdefault(hid, []).append(
            (d, az if az is not None else 0.0, dip if dip is not None else -90.0)
        )
    intervals = {}
    for r in conn.execute("SELECT hole_id,from_depth,to_depth,lithology FROM intervals ORDER BY from_depth"):
        hid, f, t, lith = r
        intervals.setdefault(hid, []).append((f, t, lith))

    tops = {}
    for ints in intervals.values():
        for f, _t, lith in ints:
            tops.setdefault(lith, []).append(f)
    units = sorted(tops, key=lambda u: float(np.mean(tops[u])))  # somero -> profundo

    conn.close()
    return collars, surveys, intervals, units


def load_assays(assays_csv, element=None):
    """CSV de assays -> {hole_id: [(from_depth, to_depth, value), ...]} (filtrado por element)."""
    conn = create_db(":memory:")
    import_assays(conn, assays_csv)
    assays = {}
    q = "SELECT hole_id,from_depth,to_depth,value FROM assays" + (" WHERE element=?" if element else "") + " ORDER BY from_depth"
    for r in conn.execute(q, (element,) if element else ()):
        hid, f, t, v = r
        if v is not None:
            assays.setdefault(hid, []).append((f, t, v))
    conn.close()
    return assays
