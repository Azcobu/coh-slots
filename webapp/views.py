"""
Routes and data access for the coh-slots web frontend.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, render_template

from pipeline import db_schema
from .at_icons import icon_for_at
from .enh_icons import icon_for_enh
from .power_icons import icon_for_power
from .ps_icons import icon_for_ps
from pipeline.banned import is_banned
from pipeline.refdata import RefData, load as load_refdata


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SLOTS_DB = PROJECT_ROOT / "data" / "slots.sqlite"

# Kheldian inherent powers that live in Inherent.Inherent but belong on the
# Warshade / Peacebringer AT pages rather than the universal inherents list.
_WS_INHERENT_SUFFIXES = frozenset({
    "Black_Dwarf_Antagonize", "Black_Dwarf_Drain", "Black_Dwarf_Mire",
    "Black_Dwarf_Smite", "Black_Dwarf_Step", "Black_Dwarf_Strike",
    "Dark_Nova_Blast", "Dark_Nova_Bolt", "Dark_Nova_Detonation", "Dark_Nova_Emanation",
    "Shadow_Step", "Shadow_Recall", "Quantum_Acceleration",
})
_PB_INHERENT_SUFFIXES = frozenset({
    "White_Dwarf_Antagonize", "White_Dwarf_Flare", "White_Dwarf_Smite",
    "White_Dwarf_Step", "White_Dwarf_Strike", "White_Dwarf_Sublimation",
    "Bright_Nova_Blast", "Bright_Nova_Bolt", "Bright_Nova_Detonation", "Bright_Nova_Scatter",
    "Combat_Flight", "Energy_Flight",
})
_KHELDIAN_INHERENT_FULL_NAMES = frozenset(
    f"Inherent.Inherent.{s}" for s in _WS_INHERENT_SUFFIXES | _PB_INHERENT_SUFFIXES
)


# ── refdata cached per-process ──────────────────────────────────────────────

_REFDATA: RefData | None = None


def get_refdata() -> RefData:
    global _REFDATA
    if _REFDATA is None:
        _REFDATA = load_refdata()
    return _REFDATA


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(str(SLOTS_DB))
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── helpers ──────────────────────────────────────────────────────────────────

def _slug_to_at(slug: str, refdata: RefData) -> str | None:
    """Map a URL slug back to a canonical archetype display name."""
    target = slug.lower().replace("-", " ")
    for name in refdata.powers_tree.keys():
        if name.startswith("_"):
            continue
        if name.lower() == target:
            return name
    return None


def at_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def _stats_for_powers(power_full_names: list[str]) -> dict[str, dict]:
    """Return power_full_name -> stats row (dict) for the given powers."""
    if not power_full_names:
        return {}
    db = get_db()
    placeholders = ",".join("?" * len(power_full_names))
    rows = db.execute(
        f"SELECT power_full_name, n_taken, mean_slots, median_slots, "
        f"top_layouts_json, top_enhs_json FROM power_stats "
        f"WHERE power_full_name IN ({placeholders})",
        power_full_names,
    ).fetchall()
    out = {}
    for r in rows:
        out[r["power_full_name"]] = {
            "n_taken": r["n_taken"],
            "mean_slots": r["mean_slots"],
            "median_slots": r["median_slots"],
            "top_layouts": json.loads(r["top_layouts_json"]),
            "top_enhs": json.loads(r["top_enhs_json"]),
        }
    return out


def _powers_for_set(refdata: RefData, ps_full: str) -> list[dict]:
    """List powers in a powerset (Group.Set), ordered by level."""
    powers = []
    for fn, info in refdata.powers_index.items():
        if f"{info['group_name']}.{info['set_name']}" == ps_full:
            powers.append({
                "full_name": fn,
                "display_name": info["display_name"],
                "level": info["level"],
            })
    powers.sort(key=lambda p: (p["level"], p["display_name"]))
    return powers


def _enrich_set(refdata: RefData, ps_full: str, set_display: str,
                merge_by_display: bool = False) -> dict:
    """Build a renderable powerset block: powers + their stats.

    If merge_by_display is True, powers sharing a display name (e.g. the two
    'Sprint' records in Inherent.Inherent) are merged into one entry whose
    stats are recomputed from the union of their raw slottings."""
    powers = [p for p in _powers_for_set(refdata, ps_full)
              if not is_banned(p["display_name"])]
    stats = _stats_for_powers([p["full_name"] for p in powers])
    for p in powers:
        p["stats"] = stats.get(p["full_name"])

    if merge_by_display:
        powers = _merge_powers_by_display(powers)

    return {
        "display_name": set_display,
        "full_name": ps_full,
        "powers": powers,
    }


def _merge_powers_by_display(powers: list[dict]) -> list[dict]:
    """Group powers with the same display_name; recompute stats for groups."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for p in powers:
        if p["display_name"] not in groups:
            order.append(p["display_name"])
        groups[p["display_name"]].append(p)

    merged = []
    for name in order:
        members = groups[name]
        if len(members) == 1:
            merged.append(members[0])
        else:
            merged.append(_merge_group(members))
    return merged


def _merge_group(members: list[dict]) -> dict:
    """Merge n>1 powers into a single rendered entry by re-aggregating from
    the raw power_slotting rows for their full_names combined."""
    full_names = [m["full_name"] for m in members]
    db = get_db()
    placeholders = ",".join("?" * len(full_names))
    rows = db.execute(
        f"SELECT build_id, enh_display FROM power_slotting "
        f"WHERE power_full_name IN ({placeholders}) "
        f"AND enh_kind IN ('set', 'io') "
        f"ORDER BY build_id",
        full_names,
    ).fetchall()

    from collections import defaultdict, Counter
    from statistics import mean, median
    import json as _json

    by_build: dict[int, list[str]] = defaultdict(list)
    for build_id, enh_display in rows:
        by_build[build_id].append(enh_display)

    layouts = [tuple(sorted(enhs)) for enhs in by_build.values()]
    n_taken = len(layouts)
    if n_taken == 0:
        # All members had no data — return a synthesised empty entry.
        rep = members[0]
        return {**rep, "stats": None,
                "merged_full_names": full_names}

    slot_counts = [len(layout) for layout in layouts]
    mn = round(mean(slot_counts), 2)
    md = float(median(slot_counts))
    layout_counter = Counter(layouts)
    sorted_layouts = sorted(layout_counter.items(), key=lambda x: -x[1])

    # Match aggregator's top-N selection: 3..10 covering ~25%
    n = 3
    cum = sum(c for _, c in sorted_layouts[:n])
    while n < min(10, len(sorted_layouts)) and cum < n_taken * 25 / 100:
        n += 1
        cum = sum(c for _, c in sorted_layouts[:n])
    top_layouts = [(c, list(layout)) for layout, c in sorted_layouts[:n]]

    all_enhs = Counter()
    for layout in layouts:
        all_enhs.update(layout)
    top_enhs = [(c, e) for e, c in all_enhs.most_common(6)]

    rep = members[0]
    return {
        "full_name": rep["full_name"],   # arbitrary primary
        "display_name": rep["display_name"],
        "level": rep["level"],
        "merged_full_names": full_names,
        "stats": {
            "n_taken": n_taken,
            "mean_slots": mn,
            "median_slots": md,
            "top_layouts": top_layouts,
            "top_enhs": top_enhs,
        },
    }


# ── routes ──────────────────────────────────────────────────────────────────

def register(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    app.jinja_env.globals["at_slug"] = at_slug
    app.jinja_env.globals["at_icon"] = icon_for_at
    app.jinja_env.globals["enh_icon"] = icon_for_enh
    app.jinja_env.globals["ps_icon"] = icon_for_ps
    app.jinja_env.globals["power_icon"] = icon_for_power

    @app.route("/")
    def index():
        refdata = get_refdata()
        db = get_db()
        # Per-archetype build counts
        counts = dict(db.execute(
            "SELECT archetype, COUNT(*) FROM build GROUP BY archetype"
        ).fetchall())
        ats = []
        for name in refdata.powers_tree:
            if name.startswith("_"):
                continue
            ats.append({"name": name, "n_builds": counts.get(name, 0)})
        ats.sort(key=lambda a: a["name"])
        meta = dict(db.execute("SELECT key, value FROM scan_meta").fetchall())
        total_builds = db.execute("SELECT COUNT(*) FROM build").fetchone()[0]
        complete_builds = db.execute("SELECT COUNT(*) FROM build WHERE parsed_partial=0").fetchone()[0]
        return render_template("index.html", archetypes=ats, meta=meta,
                               total_builds=total_builds,
                               complete_builds=complete_builds)

    @app.route("/at/<slug>/")
    def archetype(slug: str):
        refdata = get_refdata()
        at_name = _slug_to_at(slug, refdata)
        if not at_name:
            abort(404)
        at_data = refdata.powers_tree[at_name]

        db = get_db()
        n_builds = db.execute(
            "SELECT COUNT(*) FROM build WHERE archetype=?", (at_name,)
        ).fetchone()[0]

        sections = []
        for role_label, role_key in (
            ("Primary", "primary"),
            ("Secondary", "secondary"),
            ("Ancillary / Epic", "epic"),
        ):
            sets = []
            for set_disp, info in sorted(at_data.get(role_key, {}).items()):
                sets.append(_enrich_set(refdata, info["full_name"], set_disp))
            sections.append({"label": role_label, "sets": sets})

        # Warshade / Peacebringer: add their inherent powers as a section.
        if at_name == "Warshade":
            suffixes = _WS_INHERENT_SUFFIXES
        elif at_name == "Peacebringer":
            suffixes = _PB_INHERENT_SUFFIXES
        else:
            suffixes = None
        if suffixes:
            full_set = _enrich_set(refdata, "Inherent.Inherent", "Inherent",
                                   merge_by_display=True)
            kept = [p for p in full_set["powers"]
                    if any(p.get("full_name", "").endswith(s) for s in suffixes)
                    or any(fn.endswith(s)
                           for s in suffixes
                           for fn in p.get("merged_full_names", []))]
            if kept:
                full_set["powers"] = kept
                sections.append({"label": "Inherent Powers", "sets": [full_set]})

        return render_template(
            "archetype.html",
            archetype=at_name,
            n_builds=n_builds,
            sections=sections,
        )

    @app.route("/pools/")
    def pools():
        refdata = get_refdata()
        sections = []

        # 1. Pool powers — keyed by display name in tree['_pools'].
        pool_sets = []
        for set_disp, info in sorted(refdata.powers_tree.get("_pools", {}).items()):
            pool_sets.append(_enrich_set(
                refdata, info["full_name"], set_disp, merge_by_display=True
            ))
        sections.append({"label": "Pool Powers", "sets": pool_sets})

        # 2. Inherent Fitness — Swift / Health / Hurdle / Stamina.
        fitness = _enrich_set(refdata, "Inherent.Fitness", "Fitness",
                              merge_by_display=True)
        sections.append({"label": "Inherent Fitness", "sets": [fitness]})

        # 3. Other inherent powers — Inherent.Inherent has 189 entries, most
        #    of them per-AT inherents (Black Dwarf forms, Blood Frenzy, etc.).
        #    Merge by display name first (collapses Sprint variants etc.),
        #    then filter to those with meaningful data.
        full_set = _enrich_set(refdata, "Inherent.Inherent", "Other Inherent",
                               merge_by_display=True)
        kept = [p for p in full_set["powers"]
                if p["stats"] and p["stats"]["n_taken"] >= 5
                and not any(fn in _KHELDIAN_INHERENT_FULL_NAMES
                            for fn in ([p.get("full_name", "")] +
                                       p.get("merged_full_names", [])))]
        if kept:
            full_set["powers"] = kept
            sections.append({"label": "Other Inherent Powers", "sets": [full_set]})

        return render_template("pools.html", sections=sections,
                               page_title="Universal Powers")

    @app.route("/notes/")
    def notes():
        db = get_db()
        n_builds = db.execute(
            "SELECT COUNT(*) FROM build WHERE parsed_partial=0"
        ).fetchone()[0]
        n_raw = db.execute("SELECT COUNT(*) FROM build").fetchone()[0]
        n_partial = n_raw - n_builds
        fmt_counts = dict(db.execute(
            "SELECT source_format, COUNT(*) FROM build WHERE parsed_partial=0 GROUP BY source_format"
        ).fetchall())
        return render_template("notes.html", n_builds=n_builds,
                               n_partial=n_partial, fmt_counts=fmt_counts)

    @app.route("/statistics/")
    def statistics_index():
        refdata = get_refdata()
        db = get_db()
        counts = dict(db.execute(
            "SELECT archetype, COUNT(*) FROM build WHERE parsed_partial=0 GROUP BY archetype"
        ).fetchall())
        ats = []
        for name in refdata.powers_tree:
            if name.startswith("_"):
                continue
            ats.append({"name": name, "n_builds": counts.get(name, 0)})
        ats.sort(key=lambda a: a["name"])

        # Powerset selectivity: average take-rate across all powers in each
        # primary/secondary powerset (min 20 builds, excludes epic/pool).
        selectivity_rows = db.execute("""
            SELECT
                ps.powerset_full_name,
                ps.n_builds,
                COUNT(pw.power_full_name) as n_powers,
                AVG(CAST(pw.n_taken AS FLOAT) / ps.n_builds) as avg_take_rate
            FROM powerset_stats ps
            JOIN power_stats pw ON pw.powerset = ps.powerset_full_name
            WHERE ps.n_builds >= 20
              AND ps.powerset_full_name NOT LIKE 'Epic.%'
            GROUP BY ps.powerset_full_name
            HAVING n_powers >= 3
            ORDER BY avg_take_rate
        """).fetchall()

        # Build reverse map: powerset full_name -> AT display name
        ps_to_at: dict[str, str] = {}
        for at_name, at_data in refdata.powers_tree.items():
            if at_name.startswith("_"):
                continue
            for role in ("primary", "secondary", "epic"):
                for ps_info in at_data.get(role, {}).values():
                    ps_to_at[ps_info["full_name"]] = at_name

        def _ps_label(full_name: str) -> str:
            ps_display = refdata.powerset_map.get(full_name, full_name.split(".")[-1])
            at_name = ps_to_at.get(full_name, "")
            return f"{ps_display} ({at_name})" if at_name else ps_display

        selectivity = [
            {
                "label": _ps_label(r[0]),
                "full_name": r[0],
                "n_builds": r[1],
                "n_powers": r[2],
                "avg_take_rate": r[3],
            }
            for r in selectivity_rows
            if r[3] is not None
        ]

        # Most popular enhancement sets overall (across all complete builds).
        # The deploy DB pre-aggregates this into top_enh_sets to avoid
        # shipping all 1.4M power_slotting rows.
        has_precomp = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='top_enh_sets'"
        ).fetchone()
        if has_precomp:
            top_enh_sets = db.execute(
                "SELECT enh_set, n FROM top_enh_sets ORDER BY n DESC LIMIT 20"
            ).fetchall()
        else:
            top_enh_sets = db.execute("""
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

        return render_template(
            "statistics_index.html",
            archetypes=ats,
            selectivity=selectivity,
            top_enh_sets=top_enh_sets,
        )

    @app.route("/statistics/<slug>/")
    def statistics_at(slug: str):
        refdata = get_refdata()
        at_name = _slug_to_at(slug, refdata)
        if not at_name:
            abort(404)
        at_data = refdata.powers_tree[at_name]
        db = get_db()

        # Prefetch all powerset denominators for this AT in one query.
        ps_full_names = [
            info["full_name"]
            for role in ("primary", "secondary", "epic")
            for info in at_data.get(role, {}).values()
        ]
        if ps_full_names:
            placeholders = ",".join("?" * len(ps_full_names))
            ps_counts = dict(db.execute(
                f"SELECT powerset_full_name, n_builds FROM powerset_stats "
                f"WHERE powerset_full_name IN ({placeholders})",
                ps_full_names,
            ).fetchall())
        else:
            ps_counts = {}

        n_total = db.execute(
            "SELECT COUNT(*) FROM build WHERE archetype=? AND parsed_partial=0",
            (at_name,),
        ).fetchone()[0]
        pairing_rows = db.execute(
            "SELECT primary_set, secondary_set, COUNT(*) as n FROM build "
            "WHERE archetype=? AND parsed_partial=0 "
            "AND primary_set IS NOT NULL AND secondary_set IS NOT NULL "
            "GROUP BY primary_set, secondary_set ORDER BY n DESC LIMIT 20",
            (at_name,),
        ).fetchall()
        pairings = [
            {
                "primary": r["primary_set"],
                "secondary": r["secondary_set"],
                "n": r["n"],
                "pct": r["n"] / n_total * 100 if n_total else 0,
            }
            for r in pairing_rows
        ]

        _MIN_BUILDS_FOR_SKIP = 20  # ignore powersets with too few builds to be meaningful

        sections = []
        skipped_candidates: list[dict] = []
        _skipped_seen: set[tuple[str, str]] = set()
        for role_label, role_key in (
            ("Primary", "primary"),
            ("Secondary", "secondary"),
            ("Ancillary / Epic", "epic"),
        ):
            powersets = []
            for set_disp, info in sorted(at_data.get(role_key, {}).items()):
                ps_full = info["full_name"]
                n_builds = ps_counts.get(ps_full, 0)

                powers = _powers_for_set(refdata, ps_full)
                stats_map = _stats_for_powers([p["full_name"] for p in powers])

                power_rows = []
                for p in powers:
                    if is_banned(p["display_name"]):
                        continue
                    s = stats_map.get(p["full_name"])
                    n_taken = s["n_taken"] if s else 0
                    take_rate = n_taken / n_builds if n_builds > 0 else None
                    power_rows.append({
                        "display_name": p["display_name"],
                        "level": p["level"],
                        "n_taken": n_taken,
                        "take_rate": take_rate,
                    })
                    key = (set_disp, p["display_name"])
                    if (role_key != "epic"
                            and n_builds >= _MIN_BUILDS_FOR_SKIP and take_rate is not None
                            and key not in _skipped_seen):
                        _skipped_seen.add(key)
                        skipped_candidates.append({
                            "powerset": set_disp,
                            "display_name": p["display_name"],
                            "n_taken": n_taken,
                            "n_builds": n_builds,
                            "take_rate": take_rate,
                        })
                power_rows.sort(key=lambda r: -(r["take_rate"] or 0))

                powersets.append({
                    "display_name": set_disp,
                    "full_name": ps_full,
                    "n_builds": n_builds,
                    "powers": power_rows,
                })
            sections.append({"label": role_label, "powersets": powersets})

        skipped_candidates.sort(key=lambda r: r["take_rate"])
        most_skipped = skipped_candidates[:10]

        return render_template(
            "statistics_at.html",
            archetype=at_name,
            n_total=n_total,
            pairings=pairings,
            most_skipped=most_skipped,
            sections=sections,
        )
