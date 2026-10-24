"""Schema SQLite de sondajes (especificación canónica en PLAN.md)."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS collars (
    hole_id TEXT PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL,
    max_depth REAL, azimuth REAL, dip REAL
);
CREATE TABLE IF NOT EXISTS surveys (
    hole_id TEXT NOT NULL, depth REAL NOT NULL, azimuth REAL, dip REAL,
    PRIMARY KEY (hole_id, depth)
);
CREATE TABLE IF NOT EXISTS intervals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, hole_id TEXT NOT NULL,
    from_depth REAL NOT NULL, to_depth REAL NOT NULL, lithology TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assays (
    id INTEGER PRIMARY KEY AUTOINCREMENT, hole_id TEXT NOT NULL,
    from_depth REAL NOT NULL, to_depth REAL NOT NULL, element TEXT NOT NULL, value REAL
);
"""


def create_db(path=":memory:"):
    """Abre (o crea) la base y asegura el schema. Devuelve la conexión."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
