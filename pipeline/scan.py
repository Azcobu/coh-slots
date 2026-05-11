"""
Scanner: read posts from archive.sqlite, extract builds, write to slots.sqlite.

Per-post precedence: MBD > MxDz > text. Cross-author dedup via the build
signature (see common.BuildRecord.signature). Failures are logged to
parse_failure rather than aborting.

Usage:
    python -m pipeline.scan [--limit N] [--reset]
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from . import db_schema
from .refdata import load as load_refdata
from .extractors import mbd as mbd_ex
from .extractors import mxdz as mxdz_ex
from .extractors import text as text_ex
from .extractors import text_v2 as text_v2_ex
from .extractors.common import BuildRecord


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DB = PROJECT_ROOT / "data" / "archive.sqlite"


def _has_marker(body: str, marker: str) -> bool:
    return marker in body


def _extract_for_post(refdata, post_id: int, body_html: str):
    """
    Try MBD → MxDz → text in priority order. Yield BuildRecord(s) from
    whichever succeeded first (per-format, not per-block: if any MBD block
    yielded a record, skip MxDz/text on this post).
    """
    if "MBD;" in body_html:
        records = list(mbd_ex.extract(refdata, post_id, body_html))
        if any(r.powers for r in records):
            yield from (r for r in records if r.powers)
            return

    if "MxDz;" in body_html or "MxDu;" in body_html:
        records = list(mxdz_ex.extract(refdata, post_id, body_html))
        if any(r.powers for r in records):
            yield from (r for r in records if r.powers)
            return

    # Newer Mids Reborn v3.6+ format (lowercase 'powerset:'). Marker is
    # 'Build plan made with Mids' or, for builds pasted without the banner,
    # the bare 'Primary powerset:' header.
    if "Build plan made with Mids" in body_html or "Primary powerset:" in body_html:
        records = list(text_v2_ex.extract(refdata, post_id, body_html))
        if any(r.powers for r in records):
            yield from (r for r in records if r.powers)
            return

    # Older Mids' Hero/Villain Designer format. Banner may be missing if the
    # build was pasted partial — fall back to the 'Primary Power Set:' header.
    if ("Plan by Mids" in body_html or "built using Mids" in body_html
            or "Primary Power Set:" in body_html):
        yield from (r for r in text_ex.extract(refdata, post_id, body_html) if r.powers)


# Builds get parsed_partial=1 (and are excluded from aggregate stats) if:
#   - more than _UNKNOWN_THRESHOLD of their enhancements failed to resolve
#     (typical of old-DB-version exports or quote munging), OR
#   - they have fewer than _MIN_SLOTTED_POWERS slotted powers — these are
#     usually asking-for-help skeletons rather than complete builds. The
#     12 threshold sits in a clear bimodal gap (real builds cluster at
#     22-31 slotted powers; the tail below ~15 is stubs).
_UNKNOWN_THRESHOLD = 0.5
_MIN_SLOTTED_POWERS = 12


def _flag_partial(rec: BuildRecord) -> None:
    if len(rec.powers) < _MIN_SLOTTED_POWERS:
        rec.parsed_partial = True
        return
    total = sum(len(p.enhancements) for p in rec.powers)
    if total == 0:
        return
    unknown = sum(1 for p in rec.powers for e in p.enhancements if e.kind == "unknown")
    if unknown / total > _UNKNOWN_THRESHOLD:
        rec.parsed_partial = True


def _insert_record(conn: sqlite3.Connection, rec: BuildRecord) -> bool:
    """
    Insert a BuildRecord. Returns True if inserted, False if dropped as a
    cross-author duplicate (signature collision).
    """
    _flag_partial(rec)
    sig = rec.signature()
    cur = conn.execute(
        "INSERT OR IGNORE INTO build "
        "(post_id, block_index, source_format, archetype, primary_set, "
        "secondary_set, epic_set, signature, parsed_partial) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (rec.post_id, rec.block_index, rec.source_format, rec.archetype,
         rec.primary_set, rec.secondary_set, rec.epic_set, sig,
         1 if rec.parsed_partial else 0),
    )
    if cur.rowcount == 0:
        return False
    build_id = cur.lastrowid
    rows = []
    for p in rec.powers:
        for i, enh in enumerate(p.enhancements):
            rows.append((
                build_id, p.power_full_name, i,
                enh.uid, enh.display, enh.set_name, enh.kind, enh.io_level,
            ))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO power_slotting "
            "(build_id, power_full_name, slot_index, enh_uid, enh_display, "
            "enh_set, enh_kind, io_level) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
    return True


def scan(limit: int | None = None, reset: bool = True) -> None:
    refdata = load_refdata()
    conn = db_schema.initialize(drop=reset)

    archive = sqlite3.connect(str(ARCHIVE_DB))
    archive.row_factory = sqlite3.Row

    sql = ("SELECT post_id, body_html FROM posts WHERE "
           "body_html LIKE '%MBD;%' OR body_html LIKE '%MxDz;%' "
           "OR body_html LIKE '%MxDu;%' OR body_html LIKE '%Plan by Mids%' "
           "OR body_html LIKE '%built using Mids%' "
           "OR body_html LIKE '%Build plan made with Mids%' "
           "OR body_html LIKE '%Primary Power Set:%'")
    if limit:
        sql += f" LIMIT {int(limit)}"

    n_posts = 0
    n_records = 0
    n_dupes = 0
    counts = {"MBD": 0, "MxDz": 0, "text": 0}

    start = time.time()
    for row in archive.execute(sql):
        n_posts += 1
        try:
            for rec in _extract_for_post(refdata, row["post_id"], row["body_html"]):
                inserted = _insert_record(conn, rec)
                if inserted:
                    n_records += 1
                    counts[rec.source_format] = counts.get(rec.source_format, 0) + 1
                else:
                    n_dupes += 1
        except Exception as e:
            conn.execute(
                "INSERT INTO parse_failure (post_id, source_format, error, detail) "
                "VALUES (?,?,?,?)",
                (row["post_id"], "?", type(e).__name__, str(e)[:500]),
            )
        if n_posts % 500 == 0:
            print(f"  {n_posts} posts, {n_records} records, {n_dupes} dupes ({time.time()-start:.1f}s)")
            conn.commit()

    conn.commit()
    elapsed = time.time() - start
    print(f"\nDone. {n_posts} posts processed, {n_records} unique builds, {n_dupes} duplicates skipped.")
    print(f"  By format: {counts}")
    print(f"  Elapsed: {elapsed:.1f}s")

    conn.execute(
        "INSERT OR REPLACE INTO scan_meta (key, value) VALUES "
        "('last_scan_at', datetime('now')), ('n_records', ?), ('n_posts', ?)",
        (str(n_records), str(n_posts)),
    )
    conn.commit()
    conn.close()
    archive.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="only scan first N candidate posts (for testing)")
    ap.add_argument("--no-reset", action="store_true",
                    help="don't drop existing slots.sqlite first")
    args = ap.parse_args()
    scan(limit=args.limit, reset=not args.no_reset)
