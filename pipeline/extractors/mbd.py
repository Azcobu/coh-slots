"""
MBD extractor.

MBD blocks are base64 + brotli + JSON. The JSON gives canonical full power
names and enhancement UIDs directly — no resolution is needed beyond looking
up the UID's display name.

JSON shape (per sample):
    {
      "BuiltWith": ..., "Level": "49", "Class": "Class_Brute",
      "Origin": "Magic", "Alignment": "Villain", "Name": "...",
      "PowerSets": [<full powerset names ordered: pri, sec, ?epic, ?pools...>],
      "PowerEntries": [
        {
          "Level": <int>, "PowerName": "<Group.Set.Power>",
          "StatInclude": <bool>, "ProcInclude": <bool>,
          "InherentSlotsUsed": <int>, "VariableValue": <int>,
          "SlotEntries": [
            {
              "Level": <int>, "IsInherent": <bool>,
              "Enhancement": {
                "Uid": "Crafted_...",
                "IoLevel": <int>, "RelativeLevel": "Even"|"PlusFive"|...,
                "Grade": "None"|"...", "Obtained": <bool>
              } or null,
              "FlippedEnhancement": ...
            }
          ],
          "SubPowerEntries": [...]
        }, ...
      ]
    }
"""
from __future__ import annotations

import base64
import brotli
import json
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


def _decode_mbd_payload(raw_block: str) -> dict:
    """Strip the header line, base64-decode, brotli-decompress, JSON-parse."""
    lines = [l for l in raw_block.splitlines() if l]
    if not lines:
        raise ValueError("empty block")
    payload = "".join(line.strip("|") for line in lines[1:])
    return json.loads(brotli.decompress(base64.b64decode(payload)))


def _powerset_display(refdata: RefData, full_name: str) -> str | None:
    return refdata.powerset_map.get(full_name)


def _classify_powersets(refdata: RefData, archetype: str | None,
                        powerset_full_names: list[str]
                        ) -> tuple[str | None, str | None, str | None]:
    """
    Identify primary, secondary, epic from the build's PowerSets list.
    Uses the powers_tree archetype entry; falls back to set_type heuristics.
    """
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


def _slot_enh_from_uid(refdata: RefData, uid: str, io_level: int | None) -> SlotEnh | None:
    """Build a SlotEnh from a UID, filtering to tracked kinds (set/io)."""
    if not uid:
        return None
    meta = refdata.meta_for_uid(uid)
    if not meta:
        # Unknown UID — keep it as an unresolved entry so dedup signature is
        # stable; mark it tracked-by-default since we can't classify.
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
    """Yield BuildRecord(s) for every MBD block in the post body."""
    text = html_to_text(body_html)
    blocks = find_build_blocks(text)
    block_idx = 0
    for kind, raw in blocks:
        if kind != "MBD":
            continue
        try:
            data = _decode_mbd_payload(raw)
        except Exception as e:
            yield _failure(post_id, block_idx, "decode", str(e))
            block_idx += 1
            continue

        record = BuildRecord(
            post_id=post_id,
            block_index=block_idx,
            source_format="MBD",
            archetype=refdata.archetype_map.get(data.get("Class", ""), data.get("Class")),
        )
        ps_list = data.get("PowerSets") or []
        record.primary_set, record.secondary_set, record.epic_set = _classify_powersets(
            refdata, record.archetype, ps_list
        )

        for pe in data.get("PowerEntries") or []:
            full_name = pe.get("PowerName")
            if not full_name:
                continue
            disp = refdata.powers_index.get(full_name, {}).get("display_name", "")
            if is_banned(disp):
                continue
            slot_entries = pe.get("SlotEntries") or []
            enhancements: list[SlotEnh] = []
            for se in slot_entries:
                enh_obj = se.get("Enhancement") if se else None
                if not enh_obj:
                    continue
                uid = enh_obj.get("Uid")
                io_level = enh_obj.get("IoLevel")
                slot_enh = _slot_enh_from_uid(refdata, uid, io_level)
                if slot_enh is not None:
                    enhancements.append(slot_enh)
            if enhancements:
                record.powers.append(PowerSlotting(
                    power_full_name=full_name,
                    enhancements=enhancements,
                ))

        yield record
        block_idx += 1


def _failure(post_id: int, block_idx: int, error: str, detail: str) -> BuildRecord:
    """A sentinel BuildRecord representing a parse failure (parsed_partial=True, no powers)."""
    return BuildRecord(
        post_id=post_id, block_index=block_idx, source_format="MBD",
        parsed_partial=True,
    )
