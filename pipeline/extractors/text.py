"""
Text-build extractor.

Mids' plain-text export looks like:

    Hero Plan by Mids' Reborn : Hero Designer 2.6.0.7
    ...
    Rathstar NRGx2: Level 50 Science Blaster
    Primary Power Set: Energy Blast
    Secondary Power Set: Energy Manipulation
    Power Pool: Flight
    Ancillary Pool: Mace Mastery
    ...
    Level 1: Power Bolt -- Thn-Acc/Dmg(A), Thn-Dmg/EndRdx(3), Thn-Dmg/Rchg(3), ...
    Level 2: Power Blast -- SprDfnBrr-Acc/Dmg(A), SprDfnBrr-Dmg/Rchg(7), ...
    ...

Each power line: `Level <N>: <PowerDisplayName> -- <abbrev>(<slot>), ...`
  - `(A)` marks the inherent first slot; numbers are added slots.
  - Enhancements use the abbrev_to_display.json keys (e.g. 'PrfShf-End%').
  - Empty/blank slots skipped. Powers with only `Empty(A)` contribute nothing.

Power-name → canonical full_name resolution uses the build header to constrain
candidates: only powers from the build's primary/secondary/epic powersets, the
pools it draws on, and inherent powersets are eligible.
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator

from .common import (
    BuildRecord,
    PowerSlotting,
    SlotEnh,
    html_to_text,
)
from ..refdata import RefData
from ..banned import is_banned


_BUILD_HEADER_MARKER = re.compile(
    r"(Plan by Mids|built using Mids|Mids[' \w]*?Reborn)", re.IGNORECASE
)
# Fallback marker: when no Mids version banner is present (build pasted
# partial, quoted-and-trimmed, or output from a non-Mids planner that
# follows the same conventions). The 'Primary Power Set:' line is the most
# reliable Mids-format signal and is unique enough not to false-positive.
_BUILD_FALLBACK_MARKER = re.compile(r"^Primary Power Set:", re.MULTILINE)

# "Rathstar NRGx2: Level 50 Science Blaster"
_AT_LINE = re.compile(r"Level\s+\d+\s+\w+\s+(?P<at>[A-Z][\w ]+?)\s*$")

# "Primary Power Set: Energy Blast"
_PRIMARY = re.compile(r"^Primary Power Set:\s*(.+?)\s*$", re.MULTILINE)
_SECONDARY = re.compile(r"^Secondary Power Set:\s*(.+?)\s*$", re.MULTILINE)
_ANCILLARY = re.compile(r"^Ancillary Pool:\s*(.+?)\s*$", re.MULTILINE)
_POOL = re.compile(r"^Power Pool:\s*(.+?)\s*$", re.MULTILINE)

# "Level 12: Hover -- LucoftheG-Def/Rchg+(A), LucoftheG-Def(31), ..."
# Also matches "Level 1: Defiance" (no enh portion).
_POWER_LINE = re.compile(
    r"^Level\s+(\d+):\s*(?P<power>[^-\n]+?)(?:\s+--\s+(?P<enhs>.*))?$",
    re.MULTILINE,
)

# Enhancement token: "Abbrev(slot)" where slot is 'A' (inherent) or a number.
# The abbreviation may itself contain parens — e.g. 'CaltoArm-+Def(Pets)' or
# 'ShlWal-ResDam/Re TP(Any)' — so we anchor on the *trailing* paren whose
# content matches the slot pattern, not the first '(' we see.
_ENH_TOKEN = re.compile(r"\s*(?P<abbrev>[^,]+?)\((?P<slot>A|\d+)\)\s*")

# Long-form (Format B): older Mids exports list each slot on its own line:
#   Level 1: Gloom
#    (A) Thunderstrike - Accuracy/Damage
#    (3) Thunderstrike - Damage/Endurance
# The slot indicator is in parens, then a hyphen separates the set name from
# the enhancement name. Slot is 'A' or a number; the rest is unconstrained.
_LONG_SLOT_LINE = re.compile(
    r"^\s*\((?P<slot>A|\d+)\)\s+(?P<set>[^-\n]+?)\s+-\s+(?P<enh>[^\n]+?)\s*$",
    re.MULTILINE,
)


def _find_sections(text: str) -> list[str]:
    """Yield each build region in text. A region runs from one header marker
    to the next (or end-of-text). Multi-build posts contain several. Falls
    back to splitting on `Primary Power Set:` when no Mids banner is found
    (covers builds pasted without the version line)."""
    matches = list(_BUILD_HEADER_MARKER.finditer(text))
    if not matches:
        matches = list(_BUILD_FALLBACK_MARKER.finditer(text))
    if not matches:
        return []
    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(text[start:end])
    return sections


def _detect_archetype(refdata: RefData, header: str) -> str | None:
    """Find the archetype display name from the build header."""
    at_displays = sorted(refdata.archetype_map.values(), key=len, reverse=True)
    # Look for "Level NN <Origin> <AT>" on a line — origin can be Magic, Mutation, etc.
    for line in header.splitlines()[:30]:
        for at in at_displays:
            # Match against last word(s) of an early "Level NN ... <AT>" line
            if re.search(rf"Level\s+\d+\s+\S+\s+{re.escape(at)}\b", line):
                return at
    # Fallback: any line containing exactly one AT name
    for line in header.splitlines()[:30]:
        for at in at_displays:
            if at in line:
                return at
    return None


def _powerset_full_for_at(refdata: RefData, archetype: str | None,
                           role: str, set_display: str) -> str | None:
    """Look up '<role>' powerset full_name for an archetype by display name."""
    if not archetype or not set_display:
        return None
    at_data = refdata.powers_tree.get(archetype, {})
    info = at_data.get(role, {}).get(set_display)
    return info["full_name"] if info else None


def _pool_full(refdata: RefData, set_display: str) -> str | None:
    info = refdata.powers_tree.get("_pools", {}).get(set_display)
    return info["full_name"] if info else None


def _build_allowed_powersets(refdata: RefData, archetype: str | None,
                              primary: str | None, secondary: str | None,
                              ancillary: str | None, pools: list[str]
                              ) -> set[str]:
    """Return the set of powerset full_names eligible for power resolution."""
    allowed: set[str] = set()
    for role, set_disp in [("primary", primary), ("secondary", secondary), ("epic", ancillary)]:
        fn = _powerset_full_for_at(refdata, archetype, role, set_disp or "")
        if fn:
            allowed.add(fn)
    for pool_disp in pools:
        fn = _pool_full(refdata, pool_disp)
        if fn:
            allowed.add(fn)
    # Always permit inherent groups (Health/Stamina/Sprint/Rest/etc).
    allowed.update({
        "Inherent.Inherent",
        "Inherent.Fitness",
        "Pool.Inherent",
        "Pool.Inherent_Fitness",
    })
    return allowed


def _resolve_power(refdata: RefData, display_name: str,
                    allowed_sets: set[str]) -> str | None:
    """
    Resolve a power display name to a canonical full_name. Constrained to
    the build's allowed powersets.
    """
    candidates = refdata.name_resolvers["by_display_name"].get(display_name.lower())
    if not candidates:
        return None
    # Filter to candidates whose powerset full_name is in allowed_sets
    matches = []
    for fn in candidates:
        # full_name = Group.Set.Power → strip last segment
        parts = fn.rsplit(".", 1)
        if len(parts) != 2:
            continue
        ps_full = parts[0]
        if ps_full in allowed_sets:
            matches.append(fn)
        # Also allow inherent powers from any inherent group
        elif ps_full.startswith("Inherent.") or ps_full.startswith("Pool.Inherent"):
            matches.append(fn)

    if not matches:
        return None
    return matches[0]  # first (insertion-ordered) wins on ties


def _resolve_enhancement(refdata: RefData, abbrev: str) -> SlotEnh | None:
    """Look up an abbreviation and produce a SlotEnh, or None to skip."""
    abbrev = abbrev.strip()
    if abbrev.startswith('?:'):
        abbrev = abbrev[2:]
    if not abbrev or abbrev in ("Empty", "Empt", "-"):
        return None
    # Strip trailing ':NN' IO-level marker (e.g. 'BlsoftheZ-Travel:50').
    if ":" in abbrev:
        head, _, tail = abbrev.rpartition(":")
        if tail.isdigit():
            abbrev = head
    # Historical aliases — older Mids exports used different short-forms.
    abbrev = _ABBREV_ALIASES.get(abbrev, abbrev)
    display = refdata.display_for_abbrev(abbrev)
    if not display and abbrev.endswith("-I"):
        # Generic IO suffix in text exports: 'EndRdx-I' -> 'EndRdx' in DB.
        display = refdata.display_for_abbrev(abbrev[:-2])
    if not display and abbrev.startswith("HO:"):
        # Hamidon-Origin: 'HO:Cyto' -> 'Cyto'.
        display = refdata.display_for_abbrev(abbrev[3:])
    if not display and abbrev.startswith("DS:"):
        # D-Sync: same prefix-strip pattern as HO.
        display = refdata.display_for_abbrev(abbrev[3:])
    if not display and ': ' in abbrev:
        # Abbrev looks like a display name (e.g. 'Armageddon: Accuracy/Damage/Recharge').
        # Try direct display lookup with the same normalisations used by text_v2.
        set_part, _, enh_part = abbrev.partition(': ')
        for candidate in _normalize_enh_display_simple(set_part, enh_part):
            meta = _meta_for_display(refdata, candidate)
            if meta and meta["kind"] in ("set", "io"):
                return SlotEnh(uid=meta["uid"], display=meta["display"],
                               set_name=meta.get("set") or None, kind=meta["kind"],
                               io_level=None)
    if not display:
        # Unknown abbrev — preserve as opaque token, marked tracked so it
        # doesn't silently disappear from signatures.
        return SlotEnh(uid=None, display=f"?:{abbrev}", set_name=None,
                       kind="unknown", io_level=None)
    # Need to recover meta to classify kind/set. Look up by reverse lookup
    # from display → uid (build a small per-call cache once).
    meta = _meta_for_display(refdata, display)
    if not meta:
        return SlotEnh(uid=None, display=display, set_name=None, kind="unknown")
    if meta["kind"] not in ("set", "io"):
        return None
    return SlotEnh(
        uid=meta["uid"],
        display=display,
        set_name=meta.get("set") or None,
        kind=meta["kind"],
    )


# Aliases for abbreviations that older Mids exports used. Maps the legacy
# short form to a current one that resolves via abbrev_to_display.json.
_ABBREV_ALIASES = {
    "LucoftheG-Rchg+":  "LucoftheG-Def/Rchg+",
    "SprBrtFur-Rech/Fury": "SprBrtFur-Rech/Fury%",
}

# Aliases for display names emitted by newer Mids that differ from refdata.
_DISPLAY_ALIASES = {
    "Luck of the Gambler: Recharge Speed": "Luck of the Gambler: Defense/Increased Global Recharge Speed",
    "Gift of the Ancients: Run Speed +7.5%": "Gift of the Ancients: Defense/Increased Run Speed",
}


def _normalize_enh_display_simple(set_part: str, enh_part: str) -> list[str]:
    """Candidate display strings for a 'Set: Enh' pair (used by both extractors)."""
    if ': Level ' in enh_part:
        enh_part = enh_part[:enh_part.index(': Level ')].strip()
    enh_part = enh_part.replace('Hea/', 'Heal/')
    candidates = [f"{set_part}: {enh_part}"]
    reordered = None
    if enh_part.startswith('Accuracy/'):
        reordered = enh_part[len('Accuracy/'):] + '/Accuracy'
        candidates.append(f"{set_part}: {reordered}")
    # Some refdata entries have a spurious space before the colon; try both
    # the original and (if applicable) the reordered form with that spacing.
    candidates.append(f"{set_part} : {enh_part}")
    if reordered:
        candidates.append(f"{set_part} : {reordered}")
    return candidates


# Lazy reverse-lookup cache: display -> {uid, set, kind, ...}
_DISPLAY_TO_META: dict | None = None


def _meta_for_display(refdata: RefData, display: str) -> dict | None:
    global _DISPLAY_TO_META
    if _DISPLAY_TO_META is None:
        _DISPLAY_TO_META = {}
        for uid, meta in refdata.enhancement_meta.items():
            d = meta.get("display")
            if d and d not in _DISPLAY_TO_META:
                _DISPLAY_TO_META[d] = {**meta, "uid": uid}
    display = _DISPLAY_ALIASES.get(display, display)
    return _DISPLAY_TO_META.get(display)


def extract(refdata: RefData, post_id: int, body_html: str) -> Iterator[BuildRecord]:
    text = html_to_text(body_html)
    sections = _find_sections(text)
    for block_idx, section in enumerate(sections):
        rec = _extract_one(refdata, post_id, block_idx, section)
        if rec is not None:
            yield rec


def _extract_one(refdata: RefData, post_id: int, block_idx: int,
                  section: str) -> BuildRecord | None:
    archetype = _detect_archetype(refdata, section)
    primary_match = _PRIMARY.search(section)
    secondary_match = _SECONDARY.search(section)
    ancillary_match = _ANCILLARY.search(section)
    primary = primary_match.group(1).strip() if primary_match else None
    secondary = secondary_match.group(1).strip() if secondary_match else None
    ancillary = ancillary_match.group(1).strip() if ancillary_match else None
    pools = [m.group(1).strip() for m in _POOL.finditer(section)]

    if not archetype or (not primary and not secondary):
        return None

    allowed_sets = _build_allowed_powersets(
        refdata, archetype, primary, secondary, ancillary, pools
    )

    record = BuildRecord(
        post_id=post_id,
        block_index=block_idx,
        source_format="text",
        archetype=archetype,
        primary_set=primary,
        secondary_set=secondary,
        epic_set=ancillary,
    )

    seen_powers: set[str] = set()
    power_matches = list(_POWER_LINE.finditer(section))
    for i, m in enumerate(power_matches):
        power_disp = m.group("power").strip()
        if is_banned(power_disp):
            continue
        full_name = _resolve_power(refdata, power_disp, allowed_sets)
        if not full_name or full_name in seen_powers:
            continue
        seen_powers.add(full_name)

        enhs_str = m.group("enhs")
        enhancements: list[SlotEnh] = []
        if enhs_str:
            # Format A (compact): slots on the same line, comma-separated abbrevs.
            for et in _ENH_TOKEN.finditer(enhs_str):
                slot_enh = _resolve_enhancement(refdata, et.group("abbrev"))
                if slot_enh is not None:
                    enhancements.append(slot_enh)
        else:
            # Format B (long-form): slots on subsequent lines with full names.
            block_start = m.end()
            block_end = power_matches[i + 1].start() if i + 1 < len(power_matches) else len(section)
            block = section[block_start:block_end]
            for sm in _LONG_SLOT_LINE.finditer(block):
                slot_enh = _resolve_enh_by_full_name(
                    refdata, sm.group("set"), sm.group("enh")
                )
                if slot_enh is not None:
                    enhancements.append(slot_enh)

        if enhancements:
            record.powers.append(PowerSlotting(
                power_full_name=full_name,
                enhancements=enhancements,
            ))

    return record if record.powers else None


def _resolve_enh_by_full_name(refdata: RefData, set_name: str, enh_name: str
                                ) -> SlotEnh | None:
    """Resolve an enhancement given as 'Set Name - Enh Name' (Format B) or
    'Invention - Recharge Reduction' for generic IOs."""
    set_name = set_name.strip()
    enh_name = enh_name.strip()
    if not set_name or not enh_name:
        return None
    # Handle generic IO long-form: "Invention - Recharge Reduction"
    if set_name.lower() == "invention":
        display = f"Invention: {enh_name}"
        meta = _meta_for_display(refdata, display)
    else:
        display = f"{set_name}: {enh_name}"
        meta = None
        for candidate in _normalize_enh_display_simple(set_name, enh_name):
            meta = _meta_for_display(refdata, candidate)
            if meta:
                display = candidate
                break
    if not meta:
        return SlotEnh(uid=None, display=f"?:{display}",
                       set_name=None, kind="unknown")
    if meta["kind"] not in ("set", "io"):
        return None
    return SlotEnh(
        uid=meta["uid"], display=meta["display"],
        set_name=meta.get("set") or None, kind=meta["kind"],
    )
