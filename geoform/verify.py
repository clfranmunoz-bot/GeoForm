"""Verificación end-to-end: CSVs -> modelo -> volúmenes vs. verdad analítica.

Corre el pipeline completo (importadores -> load_project -> ensamblaje ->
clasificación -> volumen) y compara contra volúmenes conocidos (docs/VERIFY.md).
"""
import csv
import os
import tempfile

import numpy as np

from .app import load_project
from .assemble import classify, layer_fields


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def run_verify():
    with tempfile.TemporaryDirectory() as tmp:
        collars, surveys, intervals = [], [], []
        # pozos 5x5 verticales; capas PLANAS en z=20 y z=50, piso 200
        for x in np.linspace(0, 40, 5):
            for y in np.linspace(0, 40, 5):
                hid = f"H{x:.0f}_{y:.0f}"
                collars.append([hid, x, y, 0.0, 200.0, 0.0, -90.0])
                surveys.append([hid, 0, 0, -90])
                surveys.append([hid, 200, 0, -90])
                intervals.append([hid, 0.0, 20.0, "Overburden"])
                intervals.append([hid, 20.0, 50.0, "Andesita"])
                intervals.append([hid, 50.0, 200.0, "Basement"])

        _write(os.path.join(tmp, "collars.csv"),
               ["hole_id", "x", "y", "z", "max_depth", "azimuth", "dip"], collars)
        _write(os.path.join(tmp, "surveys.csv"),
               ["hole_id", "depth", "azimuth", "dip"], surveys)
        _write(os.path.join(tmp, "intervals.csv"),
               ["hole_id", "from_depth", "to_depth", "lithology"], intervals)

        collars, surveys, intervals, units = load_project(
            os.path.join(tmp, "collars.csv"),
            os.path.join(tmp, "surveys.csv"),
            os.path.join(tmp, "intervals.csv"),
        )
        assert units == ["Overburden", "Andesita", "Basement"], units

        fields = layer_fields(collars, surveys, intervals, units)
        cx = np.arange(5, 40, 10)
        cz = np.arange(5, 200, 10)
        gx, gy, gz = np.meshgrid(cx, cx, cz, indexing="ij")
        centers = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
        labels = classify(centers, fields)

        vol = {
            units[k]: int((labels == k).sum()) * 10 * 10 * 10
            for k in range(len(units))
        }
        expect = {"Overburden": 32000, "Andesita": 48000, "Basement": 240000}
        for k, v in expect.items():
            assert vol[k] == v, (k, vol[k], v)
        return vol


if __name__ == "__main__":
    vol = run_verify()
    print("verify: OK  volúmenes", vol)
