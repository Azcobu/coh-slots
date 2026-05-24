"""
Reference-data layer.

Builds and loads the cached lookups derived from Mids' I12.mhd (powers
hierarchy) and EnhDB.mhd (enhancement metadata). Everything downstream
keys off these.

Outputs (in refdata/ alongside the source .mhd files):
    powers_tree.json        class -> primary/secondary/epic -> powerset -> [power dicts]
    powers_index.json       flat index: full_name -> power info, plus name->full_name resolvers
    uid_to_display.json     enh UID -> "Set: Enh Name" (or just name)
    abbrev_to_display.json  short abbrev (text-build form) -> "Set: Enh Name"
    static_idx_to_uid.json  EnhDB static_index (str) -> UID
    enhancement_meta.json   UID -> {set, kind, short_name, display}

`build()` regenerates all caches from the .mhd files. `load()` reads them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from .enhdb_parser import (
    parse_enhdb,
    build_uid_to_display_name,
    build_abbrev_to_display_name,
)
from .powers_parser import parse_i12, build_class_powerset_tree


REFDATA_DIR = PROJECT_ROOT / "refdata"
_MIDS_DB = Path.home() / "bottles/Mids/drive_c/users/blw/AppData/Roaming/LoadedCamel/MidsReborn/Databases/Homecoming"
I12_PATH = PROJECT_ROOT / "data" / "I12.mhd"
ENHDB_PATH = _MIDS_DB / "EnhDB.mhd"


# Actual type IDs as stored in EnhDB.mhd (matches Enums.eType in C# source).
ENH_TYPE_NORMAL = 1   # Training Origin
ENH_TYPE_SPECIAL = 2  # Dual / Single Origin
ENH_TYPE_INVENT = 3   # generic IO (incl. Hami-O exposures)
ENH_TYPE_SET = 4      # named set


@dataclass
class RefData:
    powers_tree: dict
    powers_index: dict           # full_name -> {display_name, group, set, level, role_hint}
    name_resolvers: dict         # see _build_name_resolvers
    archetype_map: dict          # class_name (e.g. 'Class_Brute') -> display ('Brute')
    powerset_map: dict           # 'Group.Set' -> display name
    power_static_idx_to_full: dict   # str(int) -> full_name
    uid_to_display: dict
    abbrev_to_display: dict
    static_idx_to_uid: dict      # str(int) -> uid
    enhancement_meta: dict       # uid -> {set, kind, short_name, display}
    display_to_uid: dict         # inverted uid_to_display; resolves old-schema display names

    def is_tracked_uid(self, uid: str) -> bool:
        """True if the enhancement is a tracked kind (named set or generic IO)."""
        meta = self.enhancement_meta.get(uid)
        if not meta:
            return False
        return meta["kind"] in ("set", "io")

    def display_for_uid(self, uid: str) -> str | None:
        return self.uid_to_display.get(uid)

    def display_for_abbrev(self, abbrev: str) -> str | None:
        return self.abbrev_to_display.get(abbrev)

    def display_for_static_idx(self, static_idx: int) -> str | None:
        uid = self.static_idx_to_uid.get(str(static_idx))
        return self.uid_to_display.get(uid) if uid else None

    def meta_for_uid(self, uid: str) -> dict | None:
        return self.enhancement_meta.get(uid)

    def uid_for_display(self, display: str) -> str | None:
        return self.display_to_uid.get(display)


def _kind_for_type(type_id: int) -> str:
    if type_id == ENH_TYPE_SET:
        return "set"
    # NOTE: in EnhDB, type=3 (InventO) only contains Hami-Os / Hydras / Titans.
    # Generic IOs share their UID with the underlying type 1 (TO) or 2 (SO/DO)
    # record — Mids distinguishes IO use from raw SO use only via per-slot
    # grade/io_level fields. Since serious builds essentially never use raw
    # TO/DO/SO and the user wants generic IOs counted alongside set IOs, we
    # classify TO/SO/Hami-O records all as 'io' here. This intentionally
    # over-counts the rare actual-SO slotting as a generic IO.
    if type_id in (ENH_TYPE_INVENT, ENH_TYPE_NORMAL, ENH_TYPE_SPECIAL):
        return "io"
    return f"unknown({type_id})"


def _build_powers_index(archetypes, powersets, powers, tree):
    """
    Flat lookup full_name -> {display_name, group, set, level, role_hint, archetypes}.
    role_hint is one of 'primary'/'secondary'/'epic'/'pool'/'inherent'/'other' if
    derivable; archetypes lists ATs that get this powerset (only for
    primary/secondary/epic).
    """
    index = {}
    for pw in powers:
        index[pw.full_name] = {
            "display_name": pw.display_name,
            "power_name": pw.power_name,
            "group_name": pw.group_name,
            "set_name": pw.set_name,
            "level": pw.level,
            "can_be_enhanced": pw.can_be_enhanced,
            "role_hint": "other",
            "archetypes": [],
        }

    # Annotate role + archetype membership from the tree
    for class_name, data in tree.items():
        if class_name.startswith("_"):
            continue
        for role in ("primary", "secondary", "epic"):
            for set_name, info in data.get(role, {}).items():
                ps_full = info["full_name"]
                for entry in info["powers"]:
                    fn = f"{ps_full}.{_to_power_token(entry)}"
                    # Note: tree stores display names; we need to find the matching power.
                    # Easier: iterate index entries with matching ps_full prefix.
                pass  # placeholder, replaced below

    for fn, info in index.items():
        # group.set.power form — derive role from group_name
        gn = info["group_name"].upper()
        if gn == "POOL":
            info["role_hint"] = "pool"
        elif gn == "EPIC":
            info["role_hint"] = "epic"
        elif gn == "INHERENT":
            info["role_hint"] = "inherent"

    # Mark primary/secondary using archetype tree
    for class_name, data in tree.items():
        if class_name.startswith("_"):
            continue
        for role in ("primary", "secondary"):
            for set_name, info in data.get(role, {}).items():
                ps_full = info["full_name"]
                for fn in list(index.keys()):
                    if index[fn]["group_name"] + "." + index[fn]["set_name"] == ps_full:
                        index[fn]["role_hint"] = role
                        if class_name not in index[fn]["archetypes"]:
                            index[fn]["archetypes"].append(class_name)
        for set_name, info in data.get("epic", {}).items():
            ps_full = info["full_name"]
            for fn in list(index.keys()):
                if index[fn]["group_name"] + "." + index[fn]["set_name"] == ps_full:
                    if class_name not in index[fn]["archetypes"]:
                        index[fn]["archetypes"].append(class_name)

    return index


def _to_power_token(display_name: str) -> str:
    return display_name.replace(" ", "_").replace("'", "")


def _build_name_resolvers(powers_index):
    """
    Build maps usable by the text extractor:
      by_display_name: lower(display_name) -> [list of full_name]
      by_powerset_and_display: (lower(set_display), lower(power_display)) -> full_name
      powerset_displays: lower(set_display) -> set of {full_powerset_name}
    Multiple full_names per display_name are common (e.g. "Air Superiority" appears in Flight pool *and* Martial Combat secondary).
    """
    by_display: dict[str, list[str]] = {}
    powerset_displays: dict[str, set[str]] = {}
    for fn, info in powers_index.items():
        key = info["display_name"].lower()
        by_display.setdefault(key, []).append(fn)
        ps_full = f"{info['group_name']}.{info['set_name']}"
        # tree gave us display names per powerset earlier — easier to recover
        # by reading the tree, but we can also collect raw set_name as a fallback.
    return {
        "by_display_name": by_display,
        "powerset_displays": {k: sorted(v) for k, v in powerset_displays.items()},
    }


def build():
    """Regenerate all reference caches from I12.mhd + EnhDB.mhd."""
    REFDATA_DIR.mkdir(exist_ok=True)

    print(f"Parsing {I12_PATH}...")
    archetypes, powersets, powers = parse_i12(str(I12_PATH))
    tree = build_class_powerset_tree(archetypes, powersets, powers)
    powers_index = _build_powers_index(archetypes, powersets, powers, tree)
    name_resolvers = _build_name_resolvers(powers_index)
    # Also add a powerset-display-name -> set of full_names map. We get this from
    # the tree, which preserves display names.
    ps_display_to_fullnames: dict[str, list[str]] = {}
    for class_name, data in tree.items():
        if class_name.startswith("_"):
            for set_disp, info in data.items():
                ps_display_to_fullnames.setdefault(set_disp.lower(), []).append(info["full_name"])
            continue
        for role in ("primary", "secondary", "epic"):
            for set_disp, info in data.get(role, {}).items():
                ps_display_to_fullnames.setdefault(set_disp.lower(), []).append(info["full_name"])
    name_resolvers["powerset_display_to_fullnames"] = {
        k: sorted(set(v)) for k, v in ps_display_to_fullnames.items()
    }

    archetype_map = {at.class_name: at.display_name for at in archetypes if at.class_name}
    powerset_map = {ps.full_name: ps.display_name for ps in powersets if ps.full_name}
    power_static_idx_to_full = {
        str(pw.static_index): pw.full_name for pw in powers if pw.full_name
    }

    (REFDATA_DIR / "power_static_idx_to_full.json").write_text(
        json.dumps(power_static_idx_to_full, indent=2, ensure_ascii=False)
    )

    (REFDATA_DIR / "archetype_map.json").write_text(
        json.dumps(archetype_map, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "powerset_map.json").write_text(
        json.dumps(powerset_map, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "powers_tree.json").write_text(
        json.dumps(tree, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "powers_index.json").write_text(
        json.dumps(powers_index, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "name_resolvers.json").write_text(
        json.dumps(name_resolvers, indent=2, ensure_ascii=False)
    )

    print(f"Parsing {ENHDB_PATH}...")
    enhancements, enhancement_sets = parse_enhdb(str(ENHDB_PATH))
    uid_to_display = build_uid_to_display_name(enhancements, enhancement_sets)
    abbrev_to_display = build_abbrev_to_display_name(enhancements, enhancement_sets)
    # Reclassify TO/SO records as generic IOs in the abbrev map too, so
    # "RechRdx" -> "Invention: Recharge Reduction" instead of bare
    # "Recharge Reduction" — matches the kind change in _kind_for_type.
    for enh in enhancements:
        if enh.short_name and enh.type_id in (ENH_TYPE_NORMAL, ENH_TYPE_SPECIAL):
            abbrev_to_display[enh.short_name] = f"Invention: {enh.name}"

    static_idx_to_uid = {}
    enhancement_meta = {}
    for enh in enhancements:
        if not enh.uid:
            continue
        static_idx_to_uid[str(enh.static_index)] = enh.uid
        set_name = ""
        if enh.type_id == ENH_TYPE_SET and 0 <= enh.set_index < len(enhancement_sets):
            set_name = enhancement_sets[enh.set_index].display_name
        kind = _kind_for_type(enh.type_id)

        # Display: 'Set: Name' for sets, 'Invention: Name' for everything we
        # treat as a generic IO (incl. TO/SO records reclassified above).
        if enh.type_id == ENH_TYPE_SET:
            display = uid_to_display.get(enh.uid, enh.name)
        elif kind == "io":
            display = f"Invention: {enh.name}"
            # Override the canonical map too so reverse lookups stay consistent.
            uid_to_display[enh.uid] = display
        else:
            display = uid_to_display.get(enh.uid, enh.name)

        enhancement_meta[enh.uid] = {
            "set": set_name,
            "kind": kind,
            "short_name": enh.short_name,
            "display": display,
        }

    (REFDATA_DIR / "uid_to_display.json").write_text(
        json.dumps(uid_to_display, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "abbrev_to_display.json").write_text(
        json.dumps(abbrev_to_display, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "static_idx_to_uid.json").write_text(
        json.dumps(static_idx_to_uid, indent=2, ensure_ascii=False)
    )
    (REFDATA_DIR / "enhancement_meta.json").write_text(
        json.dumps(enhancement_meta, indent=2, ensure_ascii=False)
    )

    print(f"Wrote refdata to {REFDATA_DIR}")
    print(f"  {len(powers_index)} powers, {len(tree) - 1} classes")
    print(f"  {len(uid_to_display)} enhancement UIDs, {len(abbrev_to_display)} abbreviations")


def load() -> RefData:
    """Load cached refdata. Calls build() if missing."""
    needed = [
        "powers_tree.json", "powers_index.json", "name_resolvers.json",
        "archetype_map.json", "powerset_map.json", "power_static_idx_to_full.json",
        "uid_to_display.json", "abbrev_to_display.json",
        "static_idx_to_uid.json", "enhancement_meta.json",
    ]
    if not all((REFDATA_DIR / n).exists() for n in needed):
        build()

    uid_to_display = json.loads((REFDATA_DIR / "uid_to_display.json").read_text())
    return RefData(
        powers_tree=json.loads((REFDATA_DIR / "powers_tree.json").read_text()),
        powers_index=json.loads((REFDATA_DIR / "powers_index.json").read_text()),
        name_resolvers=json.loads((REFDATA_DIR / "name_resolvers.json").read_text()),
        archetype_map=json.loads((REFDATA_DIR / "archetype_map.json").read_text()),
        powerset_map=json.loads((REFDATA_DIR / "powerset_map.json").read_text()),
        power_static_idx_to_full=json.loads((REFDATA_DIR / "power_static_idx_to_full.json").read_text()),
        uid_to_display=uid_to_display,
        abbrev_to_display=json.loads((REFDATA_DIR / "abbrev_to_display.json").read_text()),
        static_idx_to_uid=json.loads((REFDATA_DIR / "static_idx_to_uid.json").read_text()),
        enhancement_meta=json.loads((REFDATA_DIR / "enhancement_meta.json").read_text()),
        display_to_uid={v: k for k, v in uid_to_display.items()},
    )


if __name__ == "__main__":
    build()
