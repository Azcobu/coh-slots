import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture(scope="session")
def refdata():
    from pipeline.refdata import load
    return load()


@pytest.fixture
def mem_db():
    """Fresh in-memory SQLite DB with the minimal schema needed by aggregate functions."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE build (
            build_id        INTEGER PRIMARY KEY,
            post_id         INTEGER NOT NULL,
            block_index     INTEGER NOT NULL DEFAULT 0,
            source_format   TEXT    NOT NULL,
            archetype       TEXT,
            primary_set     TEXT,
            secondary_set   TEXT,
            epic_set        TEXT,
            signature       TEXT    NOT NULL,
            parsed_partial  INTEGER NOT NULL DEFAULT 0,
            author          TEXT,
            posted_at       TEXT
        );
        CREATE TABLE power_slotting (
            build_id        INTEGER NOT NULL,
            power_full_name TEXT    NOT NULL,
            slot_index      INTEGER NOT NULL,
            enh_uid         TEXT,
            enh_display     TEXT,
            enh_set         TEXT,
            enh_kind        TEXT,
            io_level        INTEGER,
            PRIMARY KEY (build_id, power_full_name, slot_index)
        );
    """)
    yield conn
    conn.close()
