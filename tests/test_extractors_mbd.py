"""Tests for MBD file parsing using real build files from data/submitted/."""
import json
from pathlib import Path

import pytest

SUBMITTED_DIR = Path(__file__).resolve().parent.parent / "data" / "submitted"
ICESPHERE_DIR = SUBMITTED_DIR / "Icesphere"
MAELWYS_DIR   = SUBMITTED_DIR / "Maelwys"

needs_icesphere = pytest.mark.skipif(
    not ICESPHERE_DIR.exists(),
    reason="data/submitted/Icesphere/ not present",
)
needs_maelwys = pytest.mark.skipif(
    not MAELWYS_DIR.exists(),
    reason="data/submitted/Maelwys/ not present",
)


# ── Old-schema display-name fallback ─────────────────────────────────────────

class TestOldSchemaFallback:
    """Old Mids format serialises Enhancement as a display-name string rather
    than {"Uid": "...", ...}.  The parser must resolve it via the reverse map."""

    def _make_old_schema_mbd(self, display_name: str, io_level: int = 49) -> bytes:
        """Return a minimal old-schema .mbd JSON with one power and one slot."""
        return json.dumps({
            "Class": "Class_Blaster",
            "PowerSets": ["Blaster_Ranged.Archery", "Blaster_Support.Gadgets"],
            "PowerEntries": [{
                "PowerName": "Blaster_Ranged.Archery.Snap_Shot",
                "SlotEntries": [{
                    "Enhancement": {
                        "Enhancement": display_name,
                        "Grade": "None",
                        "IoLevel": io_level,
                        "RelativeLevel": "Even",
                        "Obtained": False,
                    }
                }]
            }]
        }).encode()

    def test_old_schema_set_enh_resolves(self, refdata):
        """A set enhancement given as a display name must resolve to a tracked SlotEnh."""
        from fetch_attachments import _parse_mbd_file
        content = self._make_old_schema_mbd("Hecatomb: Damage", io_level=49)
        result = _parse_mbd_file(refdata, post_id=1, content=content)
        assert result is not None
        assert len(result.powers) == 1
        enh = result.powers[0].enhancements[0]
        assert enh.uid == "Crafted_Hecatomb_A"
        assert enh.kind == "set"

    def test_old_schema_unknown_display_skipped(self, refdata):
        """An unrecognised display name must not crash — the slot is silently dropped."""
        from fetch_attachments import _parse_mbd_file
        content = self._make_old_schema_mbd("Nonexistent Set: Accuracy/Damage")
        # Power has only one slot and it can't be resolved → result is None (no powers)
        result = _parse_mbd_file(refdata, post_id=1, content=content)
        assert result is None


# ── Icesphere corpus ──────────────────────────────────────────────────────────

@needs_icesphere
class TestParseMbdFile:
    def test_known_tanker_file(self, refdata):
        from fetch_attachments import _parse_mbd_file
        path = ICESPHERE_DIR / "4-star_RadBioFire_Tanker.mbd"
        result = _parse_mbd_file(refdata, post_id=1, content=path.read_bytes())
        assert result is not None, "Expected successful parse"
        assert result.archetype == "Tanker"
        assert result.parsed_partial == 0
        assert len(result.powers) > 0

    def test_result_has_tracked_enhancements(self, refdata):
        from fetch_attachments import _parse_mbd_file
        path = ICESPHERE_DIR / "4-star_RadBioFire_Tanker.mbd"
        result = _parse_mbd_file(refdata, post_id=1, content=path.read_bytes())
        total_enhs = sum(len(p.enhancements) for p in result.powers)
        assert total_enhs > 0, "Expected at least one tracked enhancement"

    def test_signature_is_stable(self, refdata):
        from fetch_attachments import _parse_mbd_file
        path = ICESPHERE_DIR / "4-star_RadBioFire_Tanker.mbd"
        content = path.read_bytes()
        r1 = _parse_mbd_file(refdata, post_id=1, content=content)
        r2 = _parse_mbd_file(refdata, post_id=99, content=content)
        # Signature must be independent of post_id (content-based dedup)
        assert r1.signature() == r2.signature()

    def test_all_returned_powers_have_enhancements(self, refdata):
        """_parse_mbd_file only adds a power to the record if it has enhancements."""
        from fetch_attachments import _parse_mbd_file
        path = ICESPHERE_DIR / "4-star_RadBioFire_Tanker.mbd"
        result = _parse_mbd_file(refdata, post_id=1, content=path.read_bytes())
        for p in result.powers:
            assert len(p.enhancements) > 0, (
                f"Power {p.power_full_name} should not be included with zero enhancements"
            )

    def test_bulk_parse_rate(self, refdata):
        """Parse every Icesphere .mbd file; all must succeed."""
        from fetch_attachments import _parse_mbd_file
        paths = sorted(ICESPHERE_DIR.glob("*.mbd"))
        assert len(paths) > 100, "Expected a meaningful corpus"

        failures = []
        for p in paths:
            result = _parse_mbd_file(refdata, post_id=1, content=p.read_bytes())
            if result is None:
                failures.append(p.name)

        rate = (len(paths) - len(failures)) / len(paths)
        assert rate >= 1.00, (
            f"Parse success rate {rate:.1%} "
            f"({len(failures)}/{len(paths)} failed).\n"
            f"First 10 failures:\n  " + "\n  ".join(failures[:10])
        )


# ── Maelwys corpus ────────────────────────────────────────────────────────────

@needs_maelwys
class TestParseMbdFileMaelwys:
    def test_bulk_parse_rate(self, refdata):
        """Parse every Maelwys .mbd file; all must succeed."""
        from fetch_attachments import _parse_mbd_file
        paths = sorted(MAELWYS_DIR.glob("*.mbd"))
        assert len(paths) > 10, "Expected a meaningful corpus"

        failures = []
        for p in paths:
            result = _parse_mbd_file(refdata, post_id=1, content=p.read_bytes())
            if result is None:
                failures.append(p.name)

        rate = (len(paths) - len(failures)) / len(paths)
        assert rate >= 1.00, (
            f"Parse success rate {rate:.1%} "
            f"({len(failures)}/{len(paths)} failed).\n"
            f"First 10 failures:\n  " + "\n  ".join(failures[:10])
        )


# ── _classify_powersets ───────────────────────────────────────────────────────

class TestClassifyPowersets:
    """Uses the session-scoped refdata fixture (real data).  Tests check that
    the function correctly maps powerset full_names to primary/secondary/epic
    display names, ignoring pool powersets and unknown entries."""

    def test_blaster_primary_secondary_epic(self, refdata):
        from pipeline.extractors.mbd import _classify_powersets
        pri, sec, epic = _classify_powersets(
            refdata, "Blaster",
            ["Blaster_Ranged.Archery", "Blaster_Support.Gadgets", "Epic.Munitions_Mastery"],
        )
        assert pri  == "Archery"
        assert sec  == "Devices"
        assert epic == "Arsenal Mastery"

    def test_no_epic_returns_none(self, refdata):
        from pipeline.extractors.mbd import _classify_powersets
        pri, sec, epic = _classify_powersets(
            refdata, "Blaster",
            ["Blaster_Ranged.Beam_Rifle", "Blaster_Support.Darkness_Manipulation"],
        )
        assert pri  == "Beam Rifle"
        assert sec  == "Darkness Manipulation"
        assert epic is None

    def test_pool_powersets_ignored(self, refdata):
        from pipeline.extractors.mbd import _classify_powersets
        pri, sec, epic = _classify_powersets(
            refdata, "Blaster",
            ["Pool.Leaping", "Pool.Speed", "Blaster_Ranged.Archery", "Blaster_Support.Gadgets"],
        )
        assert pri  == "Archery"
        assert sec  == "Devices"
        assert epic is None

    def test_none_archetype_returns_all_none(self, refdata):
        from pipeline.extractors.mbd import _classify_powersets
        result = _classify_powersets(refdata, None, ["Blaster_Ranged.Archery"])
        assert result == (None, None, None)

    def test_unknown_archetype_returns_all_none(self, refdata):
        from pipeline.extractors.mbd import _classify_powersets
        result = _classify_powersets(refdata, "Nonexistent_AT", ["Blaster_Ranged.Archery"])
        assert result == (None, None, None)

    def test_powerset_order_does_not_matter(self, refdata):
        """primary/secondary classification must be role-based, not position-based."""
        from pipeline.extractors.mbd import _classify_powersets
        pri, sec, _ = _classify_powersets(
            refdata, "Blaster",
            ["Blaster_Support.Gadgets", "Blaster_Ranged.Archery"],  # secondary first
        )
        assert pri == "Archery"
        assert sec == "Devices"
