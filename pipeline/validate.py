"""
Coverage / sanity report for slots.sqlite.

Run after `scan` to see how cleanly things parsed:
  - record counts by source format
  - count of slottings with unknown enhancements (UID couldn't be resolved)
  - top-N unresolved enhancement UIDs / displays (DB-version drift markers)
  - powers with most data, powers with no data
  - archetype coverage

Usage:
    python -m pipeline.validate [--top N]
"""
from __future__ import annotations

import argparse
from collections import Counter

from . import db_schema
from .refdata import load as load_refdata


def report(top: int = 20) -> None:
    refdata = load_refdata()
    conn = db_schema.connect()

    n_builds = conn.execute("SELECT COUNT(*) FROM build").fetchone()[0]
    n_slottings = conn.execute("SELECT COUNT(*) FROM power_slotting").fetchone()[0]
    print(f"Builds: {n_builds}    Slottings: {n_slottings}")

    print("\nBy source_format:")
    for fmt, c in conn.execute(
        "SELECT source_format, COUNT(*) FROM build GROUP BY source_format ORDER BY 2 DESC"
    ):
        print(f"  {fmt:6}  {c}")

    print("\nBy archetype:")
    for at, c in conn.execute(
        "SELECT archetype, COUNT(*) FROM build GROUP BY archetype ORDER BY 2 DESC"
    ):
        print(f"  {at!s:20} {c}")

    print("\nKinds across all slottings:")
    for kind, c in conn.execute(
        "SELECT enh_kind, COUNT(*) FROM power_slotting GROUP BY enh_kind ORDER BY 2 DESC"
    ):
        print(f"  {kind!s:8} {c}")

    print(f"\nTop {top} unresolved enhancements (kind='unknown'):")
    for disp, c in conn.execute(
        "SELECT enh_display, COUNT(*) FROM power_slotting "
        "WHERE enh_kind='unknown' GROUP BY enh_display ORDER BY 2 DESC LIMIT ?",
        (top,),
    ):
        print(f"  {c:6}  {disp}")

    print(f"\nTop {top} powers by takers (n_taken):")
    for fn, disp, ps, n in conn.execute(
        "SELECT power_full_name, display_name, powerset, n_taken "
        "FROM power_stats ORDER BY n_taken DESC LIMIT ?",
        (top,),
    ):
        print(f"  {n:5}  {disp} ({ps})")

    n_powers_in_db = len(refdata.powers_index)
    n_powers_with_stats = conn.execute("SELECT COUNT(*) FROM power_stats").fetchone()[0]
    print(f"\nPowers with stats: {n_powers_with_stats} / {n_powers_in_db} known")

    n_failures = conn.execute("SELECT COUNT(*) FROM parse_failure").fetchone()[0]
    if n_failures:
        print(f"\nParse failures: {n_failures}")
        for err, c in conn.execute(
            "SELECT error, COUNT(*) FROM parse_failure GROUP BY error ORDER BY 2 DESC LIMIT 10"
        ):
            print(f"  {c:5}  {err}")

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    report(top=args.top)
