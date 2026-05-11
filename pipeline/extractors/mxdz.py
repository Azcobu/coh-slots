"""
MxDz extractor.

Wraps mxdz_decoder.extract_mxdz + parse_mxdz_binary. Two complications vs MBD:
  1. With qualified_names=False (the common case), powers are referenced by
     static_index, not full name → resolve via refdata.power_static_idx_to_full.
  2. The build's class_uid (e.g. 'Class_Brute') and powerset names ('Group.Set')
     come through directly, same as MBD.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .common import (
    BuildRecord,
    PowerSlotting,
    SlotEnh,
    find_build_blocks,
    html_to_text,
)
from ..refdata import RefData
from ..banned import is_banned

from ..mxdz_decoder import extract_mxdz, parse_mxdz_binary, EnhLookup

# Cached EnhLookup (built from refdata on first use).
_ENH_LOOKUP: EnhLookup | None = None
_ENH_LOOKUP_REFDATA_ID: int | None = None


def _enh_lookup(refdata: 'RefData') -> EnhLookup:
    global _ENH_LOOKUP, _ENH_LOOKUP_REFDATA_ID
    rid = id(refdata)
    if _ENH_LOOKUP is None or _ENH_LOOKUP_REFDATA_ID != rid:
        _ENH_LOOKUP = EnhLookup.from_refdata(refdata.static_idx_to_uid, refdata.uid_to_display)
        _ENH_LOOKUP_REFDATA_ID = rid
    return _ENH_LOOKUP


def _classify_powersets(refdata: RefData, archetype: str | None,
                        powerset_full_names: list[str]
                        ) -> tuple[str | None, str | None, str | None]:
    if not archetype:
        return None, None, None
    at_data = refdata.powers_tree.get(archetype)
    if not at_data:
        return None, None, None
    primary_set = secondary_set = epic_set = None
    primary_fns = {info["full_name"]: name for name, info in at_data.get("primary", {}).items()}
    secondary_fns = {info["full_name"]: name for name, info in at_data.get("secondary", {}).items()}
    epic_fns = {info["full_name"]: name for name, info in at_data.get("epic", {}).items()}
    for fn in powerset_full_names:
        if fn in primary_fns and not primary_set:
            primary_set = primary_fns[fn]
        elif fn in secondary_fns and not secondary_set:
            secondary_set = secondary_fns[fn]
        elif fn in epic_fns and not epic_set:
            epic_set = epic_fns[fn]
    return primary_set, secondary_set, epic_set


def _slot_enh(refdata: RefData, uid: str | None, io_level: int | None) -> SlotEnh | None:
    if not uid:
        return None
    meta = refdata.meta_for_uid(uid)
    if not meta:
        return SlotEnh(
            uid=uid, display=uid, set_name=None, kind="unknown", io_level=io_level
        )
    if meta["kind"] not in ("set", "io"):
        return None
    return SlotEnh(
        uid=uid,
        display=meta["display"],
        set_name=meta["set"] or None,
        kind=meta["kind"],
        io_level=io_level,
    )


def extract(refdata: RefData, post_id: int, body_html: str) -> Iterable[BuildRecord]:
    text = html_to_text(body_html)
    blocks = find_build_blocks(text)
    block_idx = 0
    for kind, raw in blocks:
        if kind not in ("MxDz", "MxDu"):
            continue
        try:
            decompressed = extract_mxdz(raw)
            build = parse_mxdz_binary(decompressed, _enh_lookup(refdata))
        except Exception:
            block_idx += 1
            continue

        record = BuildRecord(
            post_id=post_id,
            block_index=block_idx,
            source_format="MxDz",
            archetype=refdata.archetype_map.get(build.class_uid, build.class_uid),
        )
        record.primary_set, record.secondary_set, record.epic_set = _classify_powersets(
            refdata, record.archetype, build.powersets
        )

        for pe in build.powers:
            # Determine canonical power_full_name
            if build.qualified_names and pe.power_name:
                full_name = pe.power_name
            elif pe.power_id is not None and pe.power_id > -1:
                full_name = refdata.power_static_idx_to_full.get(str(pe.power_id))
            else:
                full_name = None

            if not full_name:
                continue
            disp = refdata.powers_index.get(full_name, {}).get("display_name", "")
            if is_banned(disp):
                continue

            enhancements: list[SlotEnh] = []
            for s in pe.slots:
                # mxdz_decoder fills enhancement_uid when EnhLookup is provided.
                io_lvl = s.io_level + 1 if s.io_level else None
                slot_enh = _slot_enh(refdata, s.enhancement_uid or None, io_lvl)
                if slot_enh is not None:
                    enhancements.append(slot_enh)
            if enhancements:
                record.powers.append(PowerSlotting(
                    power_full_name=full_name,
                    enhancements=enhancements,
                ))

        yield record
        block_idx += 1
