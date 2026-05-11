"""
Freeze the Flask webapp into a static site under build/.

Usage:
    python scripts/freeze.py [--out DIR]

Workflow:
  1. Frozen-Flask crawls all routes and writes HTML to build/.
  2. Symlinked static assets (icons, font) are resolved by copying the real
     files into build/static/, since Cloudflare Pages can't follow symlinks
     that escape the repository root.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))


def _make_deploy_db(src: Path, dst: Path) -> None:
    """Build a trimmed deployment database from the full slots.sqlite.

    Includes all aggregated tables the webapp reads, plus a slim
    power_slotting table (3 columns, Inherent/Pool powers only) needed
    by _merge_group to recompute stats for shared-display-name powers.
    """
    import sqlite3
    if dst.exists():
        dst.unlink()
    src_con = sqlite3.connect(src)
    dst_con = sqlite3.connect(dst)

    # Full copy of small aggregated tables.
    for name in ("build", "power_stats", "powerset_stats", "scan_meta"):
        schema = src_con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()[0]
        dst_con.execute(schema)
        rows = src_con.execute(f"SELECT * FROM {name}").fetchall()
        if rows:
            placeholders = ",".join("?" * len(rows[0]))
            dst_con.executemany(f"INSERT INTO {name} VALUES ({placeholders})", rows)

    # Slim power_slotting: only columns _merge_group needs, only for
    # Inherent.* and Pool.* powers (the only ones that use merge_by_display).
    # Slim power_slotting: only columns the webapp queries, only for
    # Inherent.* and Pool.* powers (the only ones using merge_by_display).
    # Also needed: enh_set for the statistics_index top-sets query.
    dst_con.execute("""
        CREATE TABLE power_slotting (
            build_id        INTEGER NOT NULL,
            power_full_name TEXT    NOT NULL,
            slot_index      INTEGER NOT NULL,
            enh_display     TEXT,
            enh_set         TEXT,
            enh_kind        TEXT
        )
    """)
    rows = src_con.execute("""
        SELECT build_id, power_full_name, slot_index, enh_display, enh_set, enh_kind
        FROM power_slotting
        WHERE power_full_name LIKE 'Inherent.%'
           OR power_full_name LIKE 'Pool.%'
    """).fetchall()
    dst_con.executemany(
        "INSERT INTO power_slotting VALUES (?,?,?,?,?,?)", rows
    )

    # Pre-aggregate top enhancement sets so the deploy DB doesn't need all
    # 1.4M power_slotting rows (only Inherent/Pool rows are included above).
    dst_con.execute("""
        CREATE TABLE top_enh_sets (
            enh_set TEXT NOT NULL,
            n       INTEGER NOT NULL
        )
    """)
    top_rows = src_con.execute("""
        SELECT ps.enh_set, COUNT(*) as n
        FROM power_slotting ps
        JOIN build b ON b.build_id = ps.build_id
        WHERE b.parsed_partial = 0
          AND ps.enh_set IS NOT NULL
          AND ps.enh_set != ''
        GROUP BY ps.enh_set
        ORDER BY n DESC
        LIMIT 20
    """).fetchall()
    dst_con.executemany("INSERT INTO top_enh_sets VALUES (?,?)", top_rows)

    dst_con.commit()
    dst_con.execute("VACUUM")
    dst_con.close()
    src_con.close()
    size_mb = dst.stat().st_size / 1_048_576
    print(f"  Deploy DB: {dst.name} ({size_mb:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROJECT_ROOT / "build"),
                    help="Output directory (default: build/)")
    args = ap.parse_args()
    out = Path(args.out)

    from flask_frozen import Freezer
    from webapp import create_app
    from webapp.views import at_slug
    from pipeline.refdata import load as load_refdata

    app = create_app()
    app.config["FREEZER_DESTINATION"] = str(out)
    app.config["FREEZER_IGNORE_MIMETYPE_WARNINGS"] = True

    rd = load_refdata()
    ats = sorted(name for name in rd.powers_tree if not name.startswith("_"))

    freezer = Freezer(app)

    @freezer.register_generator
    def archetype():
        for at in ats:
            yield {"slug": at_slug(at)}

    @freezer.register_generator
    def statistics_at():
        for at in ats:
            yield {"slug": at_slug(at)}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Build a trimmed deployment database if the full slots.sqlite is present.
    # On Cloudflare Pages, only slots_deploy.sqlite is committed to the repo,
    # so this step is skipped and the existing deploy DB is used as-is.
    src_db = PROJECT_ROOT / "data" / "slots.sqlite"
    deploy_db = PROJECT_ROOT / "data" / "slots_deploy.sqlite"
    if src_db.exists():
        _make_deploy_db(src_db, deploy_db)
    else:
        print(f"  Using existing deploy DB: {deploy_db.name} ({deploy_db.stat().st_size / 1_048_576:.1f} MB)")

    # Point the webapp at the trimmed DB for the freeze run.
    import webapp.views as _views
    _orig_db = _views.SLOTS_DB
    _views.SLOTS_DB = deploy_db

    print(f"Freezing to {out} …")
    freezer.freeze()

    _views.SLOTS_DB = _orig_db
    print(f"  HTML done — {len(list(out.rglob('*.html')))} pages written")

    # Resolve symlinked static assets into the build output.
    # Frozen-Flask copies static/ but follows symlinks only one level deep;
    # directory symlinks that point outside the repo are not traversed.
    static_src = PROJECT_ROOT / "webapp" / "static"
    static_dst = out / "static"

    symlinks = [p for p in static_src.iterdir() if p.is_symlink()]
    print(f"  Resolving {len(symlinks)} static symlinks …")
    for link in symlinks:
        real = link.resolve()
        dst = static_dst / link.name
        if dst.exists() or dst.is_symlink():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if real.is_dir():
            shutil.copytree(real, dst)
        else:
            shutil.copy2(real, dst)
        print(f"    {link.name} -> copied from {real}")

    print(f"\nDone. Output: {out}")
    print(f"  Pages : {len(list(out.rglob('*.html')))}")
    print(f"  Assets: {len(list((static_dst).rglob('*') if static_dst.exists() else []))}")


if __name__ == "__main__":
    main()
