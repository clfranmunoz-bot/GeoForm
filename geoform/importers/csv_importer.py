"""Importadores CSV -> SQLite. Encabezados sin distinguir mayúsculas; valida en la
frontera (columnas obligatorias, números, from < to) y reporta la fila culpable."""
import csv


class ImportError_(ValueError):
    """Error de datos de entrada con archivo y fila."""


def _rows(path, required):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ImportError_(f"{path}: archivo vacío")
        names = {n.strip().lower(): n for n in reader.fieldnames}
        missing = [c for c in required if c not in names]
        if missing:
            raise ImportError_(f"{path}: faltan columnas {missing}")
        for i, row in enumerate(reader, start=2):
            yield i, {k: (row[v].strip() if row[v] is not None else "") for k, v in names.items()}


def _num(path, line, row, key, optional=False):
    v = row.get(key, "")
    if v == "":
        if optional:
            return None
        raise ImportError_(f"{path}:{line}: '{key}' vacío")
    try:
        return float(v)
    except ValueError:
        raise ImportError_(f"{path}:{line}: '{key}'={v!r} no es numérico") from None


def import_collars(conn, path):
    data = []
    for line, r in _rows(path, ["hole_id", "x", "y", "z"]):
        data.append((r["hole_id"], _num(path, line, r, "x"), _num(path, line, r, "y"), _num(path, line, r, "z"),
                     _num(path, line, r, "max_depth", True), _num(path, line, r, "azimuth", True),
                     _num(path, line, r, "dip", True)))
    conn.executemany("INSERT OR REPLACE INTO collars VALUES (?,?,?,?,?,?,?)", data)
    conn.commit()
    return len(data)


def import_surveys(conn, path):
    data = []
    for line, r in _rows(path, ["hole_id", "depth"]):
        data.append((r["hole_id"], _num(path, line, r, "depth"), _num(path, line, r, "azimuth", True),
                     _num(path, line, r, "dip", True)))
    conn.executemany("INSERT OR REPLACE INTO surveys VALUES (?,?,?,?)", data)
    conn.commit()
    return len(data)


def _check_interval(path, line, f, t):
    if t <= f:
        raise ImportError_(f"{path}:{line}: to_depth ({t}) <= from_depth ({f})")


def import_intervals(conn, path):
    data = []
    for line, r in _rows(path, ["hole_id", "from_depth", "to_depth", "lithology"]):
        f, t = _num(path, line, r, "from_depth"), _num(path, line, r, "to_depth")
        _check_interval(path, line, f, t)
        if not r["lithology"]:
            raise ImportError_(f"{path}:{line}: litología vacía")
        data.append((r["hole_id"], f, t, r["lithology"]))
    conn.executemany("INSERT INTO intervals (hole_id, from_depth, to_depth, lithology) VALUES (?,?,?,?)", data)
    conn.commit()
    return len(data)


def import_assays(conn, path):
    data = []
    for line, r in _rows(path, ["hole_id", "from_depth", "to_depth", "element", "value"]):
        f, t = _num(path, line, r, "from_depth"), _num(path, line, r, "to_depth")
        _check_interval(path, line, f, t)
        data.append((r["hole_id"], f, t, r["element"], _num(path, line, r, "value", True)))
    conn.executemany("INSERT INTO assays (hole_id, from_depth, to_depth, element, value) VALUES (?,?,?,?,?)", data)
    conn.commit()
    return len(data)
