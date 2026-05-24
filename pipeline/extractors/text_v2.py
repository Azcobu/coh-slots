"""
Newer-style Mids text-build extractor (Mids' Reborn v3.6+ format).

This format is distinct from the v1 text format (handled by text.py) in
several ways:

  * No "Plan by Mids" marker; instead "Build plan made with Mids" appears
    on its own line near the top.
  * Header uses lowercase 'powerset':
      Primary powerset: Dark Blast
      Secondary powerset: Dark Miasma
      Pool powerset (#1): Leaping
      Ancillary powerset: Ice Mastery
  * Archetype line is e.g. "Villain Corruptor" / "Hero Blaster" preceding
    the build header.
  * Each power's slot lines use *full enhancement display names*, not
    abbreviations:
        Level 2: Tar Patch
        A: Ice Mistral's Torment: Chance for Cold Damage
        9: Ice Mistral's Torment: Accuracy/Damage/Endurance/Recharge
    Slot indicator is `A` (the inherent slot) or a level number.

We resolve enhancement display names directly via the reverse map cached
in extractors.text._meta_for_display (keyed by 'Set Name: Enh Name').
"""
from __future__ import annotations

import re
from typing import Iterator

from .common import (
    BuildRecord,
    PowerSlotting,
    SlotEnh,
    html_to_text,
)
from .text import _meta_for_display, _normalize_enh_display_simple
from ..refdata import RefData
from ..banned import is_banned


_HEADER_MARKER = re.compile(r"Build plan made with Mids", re.IGNORECASE)
# Fallback when banner is missing (truncated paste, partial quote).
_HEADER_FALLBACK = re.compile(r"^Primary powerset:", re.MULTILINE)

_PRIMARY = re.compile(r"^Primary powerset:\s*(.+?)\s*$", re.MULTILINE)
_SECONDARY = re.compile(r"^Secondary powerset:\s*(.+?)\s*$", re.MULTILINE)
# 'Ancillary powerset:' (older v3.6.6) or 'Epic powerset:' (newer revs).
_ANCILLARY = re.compile(r"^(?:Ancillary|Epic) powerset:\s*(.+?)\s*$", re.MULTILINE)
_POOL = re.compile(r"^Pool powerset \(#\d+\):\s*(.+?)\s*$", re.MULTILINE)

# "Villain Corruptor" or "Techno-Bunny - Hero Blaster" — alignment word
# (Hero/Villain/Rogue/Vigilante/Loyalist/Resistance) followed by the AT,
# possibly with a character-name prefix on the same line.
_AT_LINE = re.compile(
    r"\b(?:Hero|Villain|Rogue|Vigilante|Loyalist|Resistance)[ \t]+"
    r"(?P<at>[A-Z][A-Za-z]+(?:[ \t][A-Z][A-Za-z]+)?)"
)

# "Level 12: Hover" — power line, on its own line.
_POWER_LINE = re.compile(r"^Level\s+(\d+):\s*(?P<power>.+?)\s*$", re.MULTILINE)

# Slot line: "<slot>: <Set Name>: <Enh Name>"
# slot is "A" or a number. Set/enh names contain no further colons in
# practice (verified across the archive).
_SLOT_LINE = re.compile(
    r"^(?P<slot>A|\d+):\s*(?P<set>[^:\n]+?):\s*(?P<enh>[^\n]+?)\s*$",
    re.MULTILINE,
)


def _detect_archetype(refdata: RefData, header: str) -> str | None:
    valid = set(refdata.archetype_map.values())
    for m in _AT_LINE.finditer(header):
        candidate = m.group("at").strip()
        if candidate in valid:
            return candidate
    return None


def _powerset_full_for_at(refdata: RefData, archetype: str | None,
                           role: str, set_display: str) -> str | None:
    if not archetype or not set_display:
        return None
    info = refdata.powers_tree.get(archetype, {}).get(role, {}).get(set_display)
    return info["full_name"] if info else None


def _pool_full(refdata: RefData, set_display: str) -> str | None:
    info = refdata.powers_tree.get("_pools", {}).get(set_display)
    return info["full_name"] if info else None


def _build_allowed_powersets(refdata: RefData, archetype: str | None,
                              primary: str | None, secondary: str | None,
                              ancillary: str | None, pools: list[str]
                              ) -> set[str]:
    allowed: set[str] = set()
    for role, set_disp in [("primary", primary), ("secondary", secondary), ("epic", ancillary)]:
        fn = _powerset_full_for_at(refdata, archetype, role, set_disp or "")
        if fn:
            allowed.add(fn)
    for pool_disp in pools:
        fn = _pool_full(refdata, pool_disp)
        if fn:
            allowed.add(fn)
    allowed.update({
        "Inherent.Inherent", "Inherent.Fitness",
        "Pool.Inherent", "Pool.Inherent_Fitness",
    })
    return allowed


def _resolve_power(refdata: RefData, display_name: str,
                    allowed_sets: set[str]) -> str | None:
    candidates = refdata.name_resolvers["by_display_name"].get(display_name.lower())
    if not candidates:
        return None
    matches = []
    for fn in candidates:
        parts = fn.rsplit(".", 1)
        if len(parts) != 2:
            continue
        ps_full = parts[0]
        if ps_full in allowed_sets:
            matches.append(fn)
        elif ps_full.startswith("Inherent.") or ps_full.startswith("Pool.Inherent"):
            matches.append(fn)
    return matches[0] if matches else None




def _resolve_enh_by_display(refdata: RefData, set_name: str, enh_name: str) -> SlotEnh | None:
    """Try 'Set: Enh' first; for generic IOs fall back to 'Invention: ...'."""
    if set_name.startswith('?:'):
        set_name = set_name[2:]
    meta = None
    raw = f"{set_name}: {enh_name}"
    for candidate in _normalize_enh_display_simple(set_name, enh_name):
        meta = _meta_for_display(refdata, candidate)
        if meta:
            break
    if not meta:
        # The display we record always uses 'Invention:' prefix for generic IOs.
        # If the build emits e.g. "Invention: Recharge Reduction" verbatim, it
        # will already match. But occasionally older exports omit the prefix —
        # try with it added.
        if not raw.lower().startswith("invention:"):
            meta = _meta_for_display(refdata, f"Invention: {enh_name}")
    if not meta:
        return SlotEnh(uid=None, display=f"?:{raw}", set_name=None, kind="unknown")
    if meta["kind"] not in ("set", "io"):
        return None
    return SlotEnh(
        uid=meta["uid"],
        display=meta["display"],
        set_name=meta.get("set") or None,
        kind=meta["kind"],
    )


def extract(refdata: RefData, post_id: int, body_html: str) -> Iterator[BuildRecord]:
    text = html_to_text(body_html)
    matches = list(_HEADER_MARKER.finditer(text))
    if not matches:
        matches = list(_HEADER_FALLBACK.finditer(text))
    if not matches:
        return
    for block_idx, m in enumerate(matches):
        end = matches[block_idx + 1].start() if block_idx + 1 < len(matches) else len(text)
        section = text[m.start():end]
        # The AT/character name line often appears a few lines BEFORE the
        # "Build plan made with Mids" banner. Pass a wider context (up to 500
        # chars back, clipped to end of prev match) only for AT detection;
        # power extraction still uses the tighter section to avoid leakage.
        prev_end = matches[block_idx - 1].end() if block_idx > 0 else 0
        at_context = text[max(prev_end, m.start() - 500):m.end()]
        rec = _extract_one(refdata, post_id, block_idx, section, at_context)
        if rec is not None:
            yield rec


def _extract_one(refdata: RefData, post_id: int, block_idx: int,
                  section: str, at_context: str | None = None) -> BuildRecord | None:
    archetype = _detect_archetype(refdata, at_context if at_context is not None else section)
    pri_m = _PRIMARY.search(section)
    sec_m = _SECONDARY.search(section)
    anc_m = _ANCILLARY.search(section)
    primary = pri_m.group(1).strip() if pri_m else None
    secondary = sec_m.group(1).strip() if sec_m else None
    ancillary = anc_m.group(1).strip() if anc_m else None
    pools = [m.group(1).strip() for m in _POOL.finditer(section)]

    if not archetype or (not primary and not secondary):
        return None

    allowed_sets = _build_allowed_powersets(
        refdata, archetype, primary, secondary, ancillary, pools
    )

    record = BuildRecord(
        post_id=post_id, block_index=block_idx, source_format="text",
        archetype=archetype, primary_set=primary,
        secondary_set=secondary, epic_set=ancillary,
    )

    power_matches = list(_POWER_LINE.finditer(section))
    seen_powers: set[str] = set()
    for i, pm in enumerate(power_matches):
        power_disp = pm.group("power").strip()
        if is_banned(power_disp):
            continue
        block_start = pm.end()
        block_end = power_matches[i + 1].start() if i + 1 < len(power_matches) else len(section)
        block = section[block_start:block_end]

        full_name = _resolve_power(refdata, power_disp, allowed_sets)
        if not full_name or full_name in seen_powers:
            continue
        seen_powers.add(full_name)

        enhancements: list[SlotEnh] = []
        for sm in _SLOT_LINE.finditer(block):
            slot_enh = _resolve_enh_by_display(
                refdata, sm.group("set"), sm.group("enh")
            )
            if slot_enh is not None:
                enhancements.append(slot_enh)
        if enhancements:
            record.powers.append(PowerSlotting(
                power_full_name=full_name, enhancements=enhancements,
            ))

    return record if record.powers else None
