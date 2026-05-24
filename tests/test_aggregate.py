"""Tests for compute_filtered_stats and compute_merged_stats."""
import pytest
from pipeline.aggregate import compute_filtered_stats, compute_merged_stats

POWER_A = "Blaster_Ranged.Archery.Snap_Shot"
SPRINT   = "Inherent.Inherent.Sprint"
SPRINT_P = "Inherent.Inherent.prestige_preorder_Sprintp"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build(conn, build_id, *, author=None, posted_at="2023-01-01", partial=0):
    conn.execute(
        "INSERT INTO build "
        "(build_id, post_id, block_index, source_format, archetype, "
        " primary_set, secondary_set, epic_set, signature, parsed_partial, author, posted_at) "
        "VALUES (?,1,0,'MBD','Blaster','Fire Blast','Fire Manip',NULL,?,?,?,?)",
        (build_id, f"sig{build_id}", partial, author, posted_at),
    )


def _slot(conn, build_id, power, *, slot=0, kind="set"):
    conn.execute(
        "INSERT INTO power_slotting "
        "(build_id, power_full_name, slot_index, enh_uid, enh_display, enh_set, enh_kind, io_level) "
        "VALUES (?,?,?,NULL,'Shield Bre-ResDam/EndRdx','Shield Breaker',?,NULL)",
        (build_id, power, slot, kind),
    )


# ── compute_filtered_stats ────────────────────────────────────────────────────

class TestComputeFilteredStats:
    def test_basic_n_taken(self, mem_db):
        _build(mem_db, 1); _slot(mem_db, 1, POWER_A); mem_db.commit()
        result = compute_filtered_stats(mem_db)
        assert result[POWER_A]["n_taken"] == 1

    def test_partial_builds_excluded(self, mem_db):
        _build(mem_db, 1, partial=1); _slot(mem_db, 1, POWER_A); mem_db.commit()
        assert POWER_A not in compute_filtered_stats(mem_db)

    def test_non_set_io_enh_excluded(self, mem_db):
        _build(mem_db, 1); _slot(mem_db, 1, POWER_A, kind="normal"); mem_db.commit()
        assert POWER_A not in compute_filtered_stats(mem_db)

    def test_n_taken_deduplicates_slots(self, mem_db):
        """A power with 3 slots in one build counts as n_taken=1, not 3."""
        _build(mem_db, 1)
        for s in range(3):
            _slot(mem_db, 1, POWER_A, slot=s)
        mem_db.commit()
        assert compute_filtered_stats(mem_db)[POWER_A]["n_taken"] == 1

    def test_author_in(self, mem_db):
        _build(mem_db, 1, author="Alice"); _slot(mem_db, 1, POWER_A)
        _build(mem_db, 2, author="Bob");   _slot(mem_db, 2, POWER_A)
        mem_db.commit()
        assert compute_filtered_stats(mem_db, author_in=["Alice"])[POWER_A]["n_taken"] == 1

    def test_author_exclude(self, mem_db):
        _build(mem_db, 1, author="Alice"); _slot(mem_db, 1, POWER_A)
        _build(mem_db, 2, author="Bob");   _slot(mem_db, 2, POWER_A)
        mem_db.commit()
        assert compute_filtered_stats(mem_db, author_exclude=["Alice"])[POWER_A]["n_taken"] == 1

    def test_author_exclude_keeps_null_author(self, mem_db):
        """Excluding a named author must not drop builds where author IS NULL."""
        _build(mem_db, 1, author="Alice"); _slot(mem_db, 1, POWER_A)
        _build(mem_db, 2, author=None);    _slot(mem_db, 2, POWER_A)
        mem_db.commit()
        assert compute_filtered_stats(mem_db, author_exclude=["Alice"])[POWER_A]["n_taken"] == 1

    def test_since_year(self, mem_db):
        _build(mem_db, 1, posted_at="2019-06-01"); _slot(mem_db, 1, POWER_A)
        _build(mem_db, 2, posted_at="2022-03-15"); _slot(mem_db, 2, POWER_A)
        mem_db.commit()
        assert compute_filtered_stats(mem_db, since_year=2022)[POWER_A]["n_taken"] == 1

    def test_combined_author_and_year(self, mem_db):
        _build(mem_db, 1, author="Alice", posted_at="2021-01-01"); _slot(mem_db, 1, POWER_A)
        _build(mem_db, 2, author="Alice", posted_at="2023-06-01"); _slot(mem_db, 2, POWER_A)
        _build(mem_db, 3, author="Bob",   posted_at="2023-06-01"); _slot(mem_db, 3, POWER_A)
        mem_db.commit()
        result = compute_filtered_stats(mem_db, since_year=2022, author_in=["Alice"])
        assert result[POWER_A]["n_taken"] == 1  # only build 2

    def test_stat_fields_present(self, mem_db):
        _build(mem_db, 1); _slot(mem_db, 1, POWER_A); mem_db.commit()
        stat = compute_filtered_stats(mem_db)[POWER_A]
        for key in ("n_taken", "mean_slots", "median_slots", "top_layouts", "top_enhs"):
            assert key in stat


# ── compute_merged_stats ──────────────────────────────────────────────────────

class TestComputeMergedStats:
    def test_merges_two_variants(self, mem_db):
        """Two builds, each with a different Sprint variant, merge to n_taken=2."""
        _build(mem_db, 1); _slot(mem_db, 1, SPRINT)
        _build(mem_db, 2); _slot(mem_db, 2, SPRINT_P)
        mem_db.commit()
        result = compute_merged_stats(mem_db, [SPRINT, SPRINT_P])
        assert result is not None
        assert result["n_taken"] == 2

    def test_deduplicates_build_with_both_variants(self, mem_db):
        """A build that has both Sprint variants counts only once."""
        _build(mem_db, 1)
        _slot(mem_db, 1, SPRINT,   slot=0)
        _slot(mem_db, 1, SPRINT_P, slot=0)
        mem_db.commit()
        result = compute_merged_stats(mem_db, [SPRINT, SPRINT_P])
        assert result["n_taken"] == 1

    def test_returns_none_with_no_data(self, mem_db):
        _build(mem_db, 1); mem_db.commit()
        assert compute_merged_stats(mem_db, ["Nonexistent.Power.X"]) is None

    def test_author_exclude_applied(self, mem_db):
        _build(mem_db, 1, author="JJDrakken"); _slot(mem_db, 1, SPRINT)
        _build(mem_db, 2, author="Icesphere"); _slot(mem_db, 2, SPRINT_P)
        mem_db.commit()
        result = compute_merged_stats(mem_db, [SPRINT, SPRINT_P],
                                      author_exclude=["JJDrakken"])
        assert result["n_taken"] == 1

    def test_since_year_applied(self, mem_db):
        _build(mem_db, 1, posted_at="2019-01-01"); _slot(mem_db, 1, SPRINT)
        _build(mem_db, 2, posted_at="2023-06-01"); _slot(mem_db, 2, SPRINT_P)
        mem_db.commit()
        result = compute_merged_stats(mem_db, [SPRINT, SPRINT_P], since_year=2022)
        assert result["n_taken"] == 1
