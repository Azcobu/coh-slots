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
from itertools import chain, combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))


import json
import sqlite3


def _render_layouts_html(top_layouts: list, n_taken: int, icon_fn) -> str:
    """Render layout list items as HTML matching the _powerset.html template."""
    parts = []
    for cnt, layout in top_layouts:
        pct = cnt / n_taken * 100
        items = ""
        for e in layout:
            icon = icon_fn(e)
            img = (f'<img class="enh-icon" src="/static/enh/{icon}" alt="" loading="lazy">'
                   if icon else "")
            items += f"<li>{img}{e}</li>"
        parts.append(
            f'<li><span class="cnt">{cnt}x ({pct:.0f}%):</span>'
            f'<ul class="enhs">{items}</ul></li>'
        )
    return "".join(parts)


def _render_enhs_html(top_enhs: list, icon_fn) -> str:
    """Render individual-enhancement list items as HTML."""
    parts = []
    for cnt, enh in top_enhs:
        icon = icon_fn(enh)
        img = (f'<img class="enh-icon" src="/static/enh/{icon}" alt="" loading="lazy">'
               if icon else "")
        parts.append(f'<li><span class="cnt">{cnt}x</span>{img}{enh}</li>')
    return "".join(parts)


def _power_json(stats: dict | None, icon_fn) -> dict | None:
    """Convert raw aggregate stats to the JSON shape the filter JS expects."""
    if stats is None or stats["n_taken"] == 0:
        return None
    return {
        "n_taken": stats["n_taken"],
        "mean_slots": stats["mean_slots"],
        "median_slots": stats["median_slots"],
        "layouts_html": _render_layouts_html(stats["top_layouts"], stats["n_taken"], icon_fn),
        "enhs_html": _render_enhs_html(stats["top_enhs"], icon_fn),
    }


def _count_at_builds(conn, at_name: str, since_year: int | None,
                     author_in: list[str] | None = None,
                     author_exclude: list[str] | None = None) -> int:
    where = ["parsed_partial = 0", "archetype = ?"]
    params: list = [at_name]
    if since_year is not None:
        where.append("posted_at >= ?")
        params.append(f"{since_year}-01-01")
    if author_in is not None:
        placeholders = ",".join("?" * len(author_in))
        where.append(f"author IN ({placeholders})")
        params.extend(author_in)
    elif author_exclude is not None:
        placeholders = ",".join("?" * len(author_exclude))
        where.append(f"(author IS NULL OR author NOT IN ({placeholders}))")
        params.extend(author_exclude)
    return conn.execute(
        "SELECT COUNT(*) FROM build WHERE " + " AND ".join(where), params
    ).fetchone()[0]


def _generate_filter_json(out: Path, db_path: Path, refdata, ats: list[str]) -> None:
    """Pre-generate one JSON data file per filter combination per page.

    Writes to out/ and also saves a committed copy to data/filter-json/ so
    Cloudflare builds (which lack slots.sqlite) can copy the pre-built files.
    """
    from pipeline.aggregate import compute_filtered_stats, compute_merged_stats
    from pipeline.banned import is_banned
    from webapp.enh_icons import icon_for_enh
    from webapp.views import at_slug, _KHELDIAN_INHERENT_FULL_NAMES

    committed_dir = PROJECT_ROOT / "data" / "filter-json"

    # Prefer slots.sqlite for full power_slotting coverage; fall back to
    # deploy DB (which has only Inherent/Pool rows — partial stats).
    src_db = PROJECT_ROOT / "data" / "slots.sqlite"
    conn = sqlite3.connect(str(src_db if src_db.exists() else db_path))

    # Authors with ≥500 complete builds become filter options.
    authors: list[str] = [
        r[0] for r in conn.execute(
            "SELECT author, COUNT(*) as n FROM build "
            "WHERE parsed_partial=0 AND author IS NOT NULL "
            "GROUP BY author HAVING n >= 1000 ORDER BY n DESC"
        )
    ]
    years = list(range(2020, 2027))

    # Write filter metadata — JS reads this to build the UI.
    data_dir = out / "data"
    data_dir.mkdir(exist_ok=True)
    committed_dir.mkdir(parents=True, exist_ok=True)
    meta_json = json.dumps({"authors": authors, "years": years})
    (data_dir / "filter-meta.json").write_text(meta_json, encoding="utf-8")
    (committed_dir / "filter-meta.json").write_text(meta_json, encoding="utf-8")

    # Collect pool power full_names for the pools page.
    pool_full_names: set[str] = set()
    for ps_info in refdata.powers_tree.get("_pools", {}).values():
        ps_full = ps_info["full_name"]
        for fn, info in refdata.powers_index.items():
            if f"{info['group_name']}.{info['set_name']}" == ps_full:
                if not is_banned(info["display_name"]):
                    pool_full_names.add(fn)
    for fn, info in refdata.powers_index.items():
        group_set = f"{info['group_name']}.{info['set_name']}"
        if group_set in ("Inherent.Fitness", "Inherent.Inherent"):
            if not is_banned(info["display_name"]) and fn not in _KHELDIAN_INHERENT_FULL_NAMES:
                pool_full_names.add(fn)

    # Collect per-AT power full_names.
    at_full_names: dict[str, set[str]] = {}
    for at in ats:
        fns: set[str] = set()
        roles = refdata.powers_tree.get(at, {})
        for role_sets in roles.values():
            for ps_info in role_sets.values():
                ps_full = ps_info["full_name"]
                for fn, info in refdata.powers_index.items():
                    if f"{info['group_name']}.{info['set_name']}" == ps_full:
                        if not is_banned(info["display_name"]):
                            fns.add(fn)
        at_full_names[at] = fns

    # Build display-name merge groups — powers that share a display name within
    # a scope need their stats merged across all full_names, mirroring what
    # _merge_group does in views.py (e.g. Sprint has 6 full_name variants).
    def _merge_groups(full_names: set[str]) -> list[list[str]]:
        from collections import defaultdict as _dd
        by_display: dict[str, list[str]] = _dd(list)
        for fn in full_names:
            display = refdata.powers_index.get(fn, {}).get("display_name", fn)
            by_display[display].append(fn)
        return [fns for fns in by_display.values() if len(fns) > 1]

    pool_merge_groups = _merge_groups(pool_full_names)
    at_merge_groups = {at: _merge_groups(at_full_names[at]) for at in ats}

    # Collect all unique merge groups (as frozensets) so we query each once per combo.
    all_merge_groups: list[list[str]] = []
    seen: set[frozenset] = set()
    for g in pool_merge_groups:
        k = frozenset(g)
        if k not in seen:
            seen.add(k)
            all_merge_groups.append(g)
    for gs in at_merge_groups.values():
        for g in gs:
            k = frozenset(g)
            if k not in seen:
                seen.add(k)
                all_merge_groups.append(g)

    if all_merge_groups:
        print(f"  {len(all_merge_groups)} display-name merge groups "
              f"({sum(len(g) for g in all_merge_groups)} total full_names)")

    # All "groups" that can be included or excluded.
    # 'others' represents unnamed/uncredited builders.
    # Named authors get a lowercase underscore key.
    author_key_to_name = {a.lower().replace(" ", "_"): a for a in authors}
    all_groups = ["others"] + sorted(author_key_to_name)
    full_set = frozenset(all_groups)

    def _nonempty_subsets(s):
        return chain.from_iterable(combinations(s, r) for r in range(1, len(s) + 1))

    year_keys = [("all", None)] + [(str(y), y) for y in years]

    # Total sets for progress display: (2^n_groups - 1) subsets × n_year_keys - 1 (all_all)
    n_total = (2 ** len(all_groups) - 1) * len(year_keys) - 1
    n_sets = 0

    for included_tuple in _nonempty_subsets(all_groups):
        included = frozenset(included_tuple)

        # Key for directory names: "all" when everything is included, else sorted-hyphen-joined.
        a_key = "all" if included == full_set else "-".join(sorted(included))

        # SQL filter kwargs for this author subset.
        include_others = "others" in included
        included_named = [author_key_to_name[k] for k in included if k != "others"]
        excluded_named = [a for a in authors if a.lower().replace(" ", "_") not in included]

        if included == full_set:
            filter_kw: dict = {}                        # no author restriction
        elif include_others:
            filter_kw = {"author_exclude": excluded_named}  # exclude some named authors
        elif included_named:
            filter_kw = {"author_in": included_named}       # only specific named authors
        else:
            filter_kw = {"author_exclude": authors}          # only unnamed builders

        for y_key, y_val in year_keys:
            if a_key == "all" and y_key == "all":
                continue  # baseline is already in the HTML

            key = f"{a_key}_{y_key}"
            key_dir = data_dir / key
            key_dir.mkdir(exist_ok=True)
            committed_key_dir = committed_dir / key
            committed_key_dir.mkdir(exist_ok=True)

            kw = dict(filter_kw, since_year=y_val) if y_val is not None else filter_kw
            stats = compute_filtered_stats(conn, **kw)

            # Overwrite per-full_name stats with merged stats for display-name groups,
            # storing the merged result under every full_name in the group so the JS
            # finds the correct value regardless of which full_name is in data-power.
            for group_fns in all_merge_groups:
                merged = compute_merged_stats(conn, group_fns, **kw)
                for fn in group_fns:
                    if merged is not None:
                        stats[fn] = merged
                    else:
                        stats.pop(fn, None)

            # Per-AT JSON.
            for at in ats:
                n_builds = _count_at_builds(conn, at, y_val, **filter_kw)
                powers_out = {
                    fn: _power_json(stats.get(fn), icon_for_enh)
                    for fn in at_full_names[at]
                }
                payload = json.dumps({"n_builds": n_builds, "powers": powers_out},
                                     ensure_ascii=False)
                (key_dir / f"at_{at_slug(at)}.json").write_text(payload, encoding="utf-8")
                (committed_key_dir / f"at_{at_slug(at)}.json").write_text(payload, encoding="utf-8")

            # Pools JSON.
            powers_out = {
                fn: _power_json(stats.get(fn), icon_for_enh)
                for fn in pool_full_names
            }
            payload = json.dumps({"powers": powers_out}, ensure_ascii=False)
            (key_dir / "pools.json").write_text(payload, encoding="utf-8")
            (committed_key_dir / "pools.json").write_text(payload, encoding="utf-8")

            n_sets += 1
            print(f"  {key} ({n_sets}/{n_total})")

    conn.close()
    print(f"  Filter metadata: {len(authors)} authors, {len(years)} years")


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

    print("\nGenerating filter JSON …")
    committed_filter_dir = PROJECT_ROOT / "data" / "filter-json"
    if src_db.exists():
        _generate_filter_json(out, deploy_db, rd, ats)
    elif committed_filter_dir.exists():
        # On Cloudflare Pages, slots.sqlite is not available; copy pre-built JSON.
        print("  slots.sqlite absent — copying committed filter JSON …")
        shutil.copytree(committed_filter_dir, out / "data", dirs_exist_ok=True)
        n_json = len(list(committed_filter_dir.rglob("*.json")))
        print(f"  Copied {n_json} JSON files from data/filter-json/")
    else:
        print("  WARNING: no slots.sqlite and no committed filter JSON — filter will not work")

    print(f"\nDone. Output: {out}")
    print(f"  Pages : {len(list(out.rglob('*.html')))}")
    print(f"  JSON  : {len(list(out.rglob('*.json')))}")
    print(f"  Assets: {len(list((static_dst).rglob('*') if static_dst.exists() else []))}")


if __name__ == "__main__":
    main()
