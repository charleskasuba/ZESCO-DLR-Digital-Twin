"""SQLite persistence layer for the DLR Digital Twin.

Stores:
    - telemetry: raw sensor readings + computed DLR outputs
    - events:    alert / status-transition log for operator visibility

The database file lives in ./data and is ignored by git. On Render's
ephemeral filesystem it simply re-seeds with demo data on each deploy.
"""

import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "telemetry.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    conductor_temp REAL NOT NULL,
    ambient_temp   REAL NOT NULL,
    humidity       REAL,
    wind_speed     REAL NOT NULL,
    current_load   REAL NOT NULL,
    static_rating  REAL NOT NULL,
    dynamic_rating REAL NOT NULL,
    capacity_gain_pct REAL,
    model_temp     REAL,
    sag_m          REAL,
    clearance_m    REAL,
    status         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level     TEXT NOT NULL,
    message   TEXT NOT NULL
);
"""


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_telemetry(record: dict) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO telemetry
               (timestamp, conductor_temp, ambient_temp, humidity, wind_speed,
                current_load, static_rating, dynamic_rating, capacity_gain_pct,
                model_temp, sag_m, clearance_m, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["timestamp"],
                record["conductor_temp"],
                record["ambient_temp"],
                record.get("humidity"),
                record["wind_speed"],
                record["current_load"],
                record["static_rating"],
                record["dynamic_rating"],
                record.get("capacity_gain_pct"),
                record.get("model_temp"),
                record.get("sag_m"),
                record.get("clearance_m"),
                record["status"],
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_event(level: str, message: str):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO events (timestamp, level, message) VALUES (?,?,?)",
            (message_timestamp(), level, message),
        )
        conn.commit()
    finally:
        conn.close()


def latest_telemetry():
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def last_event_level():
    conn = _connect()
    try:
        row = conn.execute("SELECT level FROM events ORDER BY id DESC LIMIT 1").fetchone()
        return row["level"] if row else None
    finally:
        conn.close()


def history(limit: int = 60):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM telemetry ORDER BY id DESC LIMIT ?) "
            "ORDER BY id ASC",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def events(limit: int = 20):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_telemetry():
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM telemetry").fetchone()["c"]
    finally:
        conn.close()


def _utcnow():
    from datetime import datetime

    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def message_timestamp():
    return _utcnow()
