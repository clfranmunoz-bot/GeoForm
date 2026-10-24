"""Desurvey por curvatura mínima (método del arco circular).

Solo stdlib (math). Convenciones geológicas:
  - dip: grados desde la horizontal, NEGATIVO hacia abajo (-90 = vertical abajo, 0 = horizontal).
  - azimuth: grados horarios desde el Norte (0=N, 90=E, 180=S, 270=W).
  - depth/md: profundidad medida desde el collar, creciente.
  - salida z: profundidad (crece hacia abajo).
"""

import math


def _inc(dip: float) -> float:
    """Inclinación desde la vertical (0=vertical abajo, 90=horizontal)."""
    return 90.0 + dip  # dip negativo abajo -> inc = 90 + dip


def desurvey(x0, y0, z0, az0, dip0, stations):
    """Devuelve lista [(x, y, z)] con el collar y cada estación.

    stations: lista de (md, azimuth, dip) ordenada por md creciente.
    """
    pts = [(x0, y0, z0)]
    x, y, z = x0, y0, z0
    md_prev = 0.0
    inc_prev = math.radians(_inc(dip0))
    azr_prev = math.radians(az0)

    for md, az, dip in stations:
        dmd = md - md_prev
        inc = math.radians(_inc(dip))
        azr = math.radians(az)

        # ángulo dogleg entre las dos direcciones
        cosb = math.cos(inc - inc_prev) - math.sin(inc_prev) * math.sin(inc) * (
            1.0 - math.cos(azr - azr_prev)
        )
        cosb = max(-1.0, min(1.0, cosb))
        beta = math.acos(cosb)
        rf = 1.0 if beta < 1e-9 else (2.0 / beta) * math.tan(beta / 2.0)

        dn = dmd / 2 * (math.sin(inc_prev) * math.cos(azr_prev) + math.sin(inc) * math.cos(azr)) * rf
        de = dmd / 2 * (math.sin(inc_prev) * math.sin(azr_prev) + math.sin(inc) * math.sin(azr)) * rf
        dv = dmd / 2 * (math.cos(inc_prev) + math.cos(inc)) * rf

        x += de
        y += dn
        z += dv
        pts.append((x, y, z))

        md_prev, inc_prev, azr_prev = md, inc, azr

    return pts


def _close(a, b, tol=1e-6):
    return abs(a - b) < tol


def demo():
    # Pozo vertical: x,y constantes, z avanza la profundidad medida.
    p = desurvey(100.0, 200.0, 0.0, az0=0.0, dip0=-90.0, stations=[(100, 0, -90), (200, 0, -90)])
    assert _close(p[0][2], 0.0) and _close(p[1][2], 100.0) and _close(p[2][2], 200.0), p
    assert _close(p[2][0], 100.0) and _close(p[2][1], 200.0), p

    # Pozo horizontal al Este: x avanza, y,z constantes.
    p = desurvey(0.0, 0.0, 50.0, az0=90.0, dip0=0.0, stations=[(100, 90, 0)])
    assert _close(p[1][0], 100.0) and _close(p[1][1], 0.0) and _close(p[1][2], 50.0), p

    print("desurvey: OK (vertical + horizontal)")


if __name__ == "__main__":
    demo()
