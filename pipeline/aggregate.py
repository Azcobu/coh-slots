"""
Aggregator: compute per-power slotting statistics from slots.sqlite.

Stats per power_full_name (one row in power_stats):
  - n_taken: number of distinct builds where this power has at least one
    tracked enhancement.
  - mean_slots / median_slots: across taken instances, the count of tracked
    enhancements per slotting.
  - top_layouts_json: list of (count, [enh_display, ...]) for the most
    common unordered enhancement tuples; chosen so the top entries cover
    ~25% of corpus, capped 3..10 (mirrors the old coh-enhscan logic).
  - top_enhs_json: list of (count, enh_display) — top 6 individual
    enhancements.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from statistics import mean, median

from . import db_schema
from .refdata import load as load_refdata


# AT-only purple sets ship in two tiers — "Superior X" (the upgraded form
# unlocked at 50+) and base "X". Players pick one or the other; counting
# them separately fragments the layout signal. We collapse "Superior <X>: "
# into "<X>: " for stats. The list of pairs was verified empirically against
# enhancement_meta — every "Superior <Y>" set has a matching "<Y>" base set.
def _normalize_display(enh_display: str) -> str:
    if enh_display.startswith("Superior "):
        return enh_display[len("Superior "):]
    return enh_display


def _select_top_layouts(layout_counts: list[tuple[tuple[str, ...], int]],
                         total: int, target_pct: int = 25,
                         min_n: int = 3, max_n: int = 10) -> list[tuple[int, list[str]]]:
    """Pick the top-N most-common layouts that cumulatively cover at least
    target_pct% of the corpus, with min_n <= N <= max_n."""
    sorted_counts = sorted(layout_counts, key=lambda x: -x[1])
    n = min_n
    cum = sum(c for _, c in sorted_counts[:n])
    while n < min(max_n, len(sorted_counts)) and cum < total * target_pct / 100:
        n += 1
        cum = sum(c for _, c in sorted_counts[:n])
    return [(c, list(layout)) for layout, c in sorted_counts[:n]]


def _build_powerset_stats(conn, refdata) -> None:
    """Count qualifying (parsed_partial=0) builds per primary/secondary/epic powerset.

    Pool powersets are skipped — there is no column in the build table that
    records which pools a build drew from, so no denominator is available.
    """
    conn.execute("DELETE FROM powerset_stats")
    role_to_col = {
        "primary": "primary_set",
        "secondary": "secondary_set",
        "epic": "epic_set",
    }
    # Build inverse map: powerset_full_name -> [(archetype, sql_col, set_display), ...]
    ps_queries: dict[str, list[tuple[str, str, str]]] = {}
    for at, roles in refdata.powers_tree.items():
        if at.startswith("_"):
            continue
        for role, sets in roles.items():
            col = role_to_col.get(role)
            if not col:
                continue
            for set_disp, info in sets.items():
                ps_full = info["full_name"]
                ps_queries.setdefault(ps_full, []).append((at, col, set_disp))

    rows = []
    for ps_full, queries in ps_queries.items():
        n_builds = 0
        for at, col, set_disp in queries:
            # col is from the hardcoded role_to_col dict — safe to interpolate.
            count = conn.execute(
                f"SELECT COUNT(*) FROM build "
                f"WHERE parsed_partial=0 AND archetype=? AND {col}=?",
                (at, set_disp),
            ).fetchone()[0]
            n_builds += count
        rows.append((ps_full, n_builds))

    conn.executemany(
        "INSERT INTO powerset_stats (powerset_full_name, n_builds) VALUES (?,?)", rows
    )
    conn.commit()
    print(f"Wrote {len(rows)} powerset_stats rows.")


def aggregate() -> None:
    conn = db_schema.connect()
    refdata = load_refdata()

    # Wipe old stats
    conn.execute("DELETE FROM power_stats")

    # Pull all (build_id, power_full_name, enh_display) rows with kind in (set, io)
    rows = conn.execute(
        "SELECT ps.build_id, ps.power_full_name, ps.enh_display "
        "FROM power_slotting ps "
        "JOIN build b ON b.build_id = ps.build_id "
        "WHERE ps.enh_kind IN ('set', 'io') "
        "AND b.parsed_partial = 0 "
        "ORDER BY ps.build_id, ps.power_full_name"
    ).fetchall()

    # Group: power_full_name -> { build_id -> [enh_display, ...] }
    per_power: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for build_id, power_full, enh_display in rows:
        per_power[power_full][build_id].append(_normalize_display(enh_display))

    written = 0
    for power_full, by_build in per_power.items():
        layouts = [tuple(sorted(enhs)) for enhs in by_build.values()]
        n_taken = len(layouts)
        slot_counts = [len(layout) for layout in layouts]
        mn = round(mean(slot_counts), 2) if slot_counts else 0.0
        md = float(median(slot_counts)) if slot_counts else 0.0

        layout_counter = Counter(layouts)
        top_layouts = _select_top_layouts(list(layout_counter.items()), n_taken)

        all_enhs = Counter()
        for layout in layouts:
            all_enhs.update(layout)
        top_enhs = [(c, e) for e, c in all_enhs.most_common(6)]

        info = refdata.powers_index.get(power_full, {})
        ps_full = f"{info.get('group_name','')}.{info.get('set_name','')}".strip(".")

        conn.execute(
            "INSERT INTO power_stats "
            "(power_full_name, display_name, powerset, role_hint, n_taken, "
            "mean_slots, median_slots, top_layouts_json, top_enhs_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (power_full, info.get("display_name"), ps_full, info.get("role_hint"),
             n_taken, mn, md,
             json.dumps(top_layouts, ensure_ascii=False),
             json.dumps(top_enhs, ensure_ascii=False)),
        )
        written += 1

    conn.commit()
    print(f"Wrote {written} power_stats rows.")

    _build_powerset_stats(conn, refdata)
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    aggregate()
