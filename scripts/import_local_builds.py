"""
Import local .mbd / .mxd / .txt build files into slots.sqlite.

Builds are attributed to a specified author with each file's modification
time as posted_at. Deduplication via build signature still applies, so
overlaps with forum-sourced builds are handled automatically.

Usage:
    python scripts/import_local_builds.py --dir data/icesphere --author Icesphere
    python scripts/import_local_builds.py --dir data/icesphere --author Icesphere --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="Directory containing build files")
    ap.add_argument("--author", required=True, help="Author name to attribute builds to")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and report without inserting")
    args = ap.parse_args()

    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        print(f"Error: {src_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    from pipeline import db_schema
    from pipeline.refdata import load as load_refdata
    from pipeline.scan import _insert_record
    from scripts.fetch_attachments import _parse_mbd_file, _parse_text_file

    refdata = load_refdata()
    slots = db_schema.connect()

    files = sorted(
        p for p in src_dir.iterdir()
        if p.suffix.lower() in {".mbd", ".mxd", ".txt"}
    )
    print(f"Found {len(files)} files in {src_dir}")

    n_inserted = n_dupe = n_fail = n_empty = 0
    for path in files:
        content = path.read_bytes()
        mtime = datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Use a synthetic post_id derived from filename so each file is distinct.
        # Deduplication is by build signature, not post_id.
        pseudo_post_id = abs(hash(path.name)) % (10 ** 9) + 10 ** 9

        try:
            if path.suffix.lower() == ".mbd":
                rec = _parse_mbd_file(refdata, pseudo_post_id, content)
            else:
                rec = _parse_text_file(refdata, pseudo_post_id, content)
        except Exception as e:
            print(f"  FAIL  {path.name}: {e}")
            n_fail += 1
            continue

        if rec is None or not rec.powers:
            n_empty += 1
            continue

        if args.dry_run:
            print(f"  [dry-run] {path.name}: AT={rec.archetype} "
                  f"primary={rec.primary_set} powers={len(rec.powers)}")
            n_inserted += 1
            continue

        try:
            inserted = _insert_record(slots, rec, author=args.author, posted_at=mtime)
            if inserted:
                n_inserted += 1
            else:
                n_dupe += 1
        except Exception as e:
            print(f"  FAIL  {path.name}: {e}")
            n_fail += 1

    if not args.dry_run:
        slots.commit()

    print(f"\nDone: {n_inserted} inserted, {n_dupe} dupes, "
          f"{n_empty} empty/unparseable, {n_fail} errors")


if __name__ == "__main__":
    main()
