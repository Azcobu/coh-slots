"""
Schema definition for slots.sqlite.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "slots.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS build (
    build_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL,
    block_index     INTEGER NOT NULL DEFAULT 0,
    source_format   TEXT NOT NULL,           -- 'MBD' | 'MxDz' | 'text'
    archetype       TEXT,                    -- canonical AT display name
    primary_set     TEXT,                    -- powerset display name
    secondary_set   TEXT,
    epic_set        TEXT,
    signature       TEXT NOT NULL,
    parsed_partial  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_build_post ON build(post_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_build_signature ON build(signature);

CREATE TABLE IF NOT EXISTS power_slotting (
    build_id        INTEGER NOT NULL REFERENCES build(build_id) ON DELETE CASCADE,
    power_full_name TEXT NOT NULL,           -- canonical, e.g. Blaster_Ranged.Archery.Snap_Shot
    slot_index      INTEGER NOT NULL,        -- ordering within the power, 0-based
    enh_uid         TEXT,                    -- canonical UID (NULL if unresolved)
    enh_display     TEXT,                    -- 'Set: Name' or 'Invention: Name'
    enh_set         TEXT,                    -- set display name (NULL for generic IO)
    enh_kind        TEXT,                    -- 'set' | 'io'
    io_level        INTEGER,                 -- nullable
    PRIMARY KEY (build_id, power_full_name, slot_index)
);
CREATE INDEX IF NOT EXISTS ix_slotting_power ON power_slotting(power_full_name);

CREATE TABLE IF NOT EXISTS parse_failure (
    post_id         INTEGER NOT NULL,
    source_format   TEXT NOT NULL,
    error           TEXT,
    detail          TEXT,
    ts              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_failure_post ON parse_failure(post_id);

CREATE TABLE IF NOT EXISTS power_stats (
    power_full_name TEXT PRIMARY KEY,
    display_name    TEXT,
    powerset        TEXT,                    -- 'Group.Set'
    role_hint       TEXT,
    n_taken         INTEGER NOT NULL,
    mean_slots      REAL,
    median_slots    REAL,
    top_layouts_json TEXT,                   -- [[count, [enh_display,...]], ...]
    top_enhs_json   TEXT                     -- [[count, enh_display], ...]
);

CREATE TABLE IF NOT EXISTS powerset_stats (
    powerset_full_name  TEXT PRIMARY KEY,
    n_builds            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize(path: Path | str = DB_PATH, *, drop: bool = False) -> sqlite3.Connection:
    """Create the schema. If drop=True, drop all tables first."""
    conn = connect(path)
    if drop:
        for tbl in ("powerset_stats", "power_stats", "parse_failure", "power_slotting", "build", "scan_meta"):
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true", help="drop & recreate")
    args = ap.parse_args()
    conn = initialize(drop=args.drop)
    print(f"Initialized schema at {DB_PATH}")
    print("Tables:", [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
