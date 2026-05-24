"""
Parser for Mids Reborn I12.mhd powers database.

Extracts a structured mapping of:
    Class -> Primary/Secondary/Epic Powersets -> Powers

Usage:
    python powers_parser.py /path/to/I12.mhd
    python powers_parser.py /path/to/I12.mhd --json output.json
    python powers_parser.py /path/to/I12.mhd --class Blaster

Requires enhdb_parser.py in the same directory (for DotNetBinaryReader and skip_effect).
"""

import json
import sys
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from .enhdb_parser import DotNetBinaryReader, skip_effect


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class Archetype:
    idx: int = 0
    display_name: str = ""
    class_name: str = ""         # e.g. "Class_Blaster"
    primary_group: str = ""      # e.g. "Blaster_Ranged"
    secondary_group: str = ""    # e.g. "Blaster_Support"
    epic_group: str = "EPIC"
    pool_group: str = "POOL"
    playable: bool = True
    class_type: int = 0
    hitpoints: int = 0
    desc_short: str = ""


@dataclass
class PowersetInfo:
    idx: int = 0
    display_name: str = ""
    full_name: str = ""         # e.g. "Blaster_Ranged.Archery"
    group_name: str = ""        # e.g. "Blaster_Ranged"
    set_name: str = ""          # e.g. "Archery"
    set_type: int = 0           # ePowerSetType enum
    at_class: str = ""          # archetype class restriction
    description: str = ""
    n_archetype: int = -1


@dataclass
class PowerInfo:
    full_name: str = ""         # e.g. "Blaster_Ranged.Archery.Snap_Shot"
    display_name: str = ""      # e.g. "Snap Shot"
    power_name: str = ""        # e.g. "Snap_Shot"
    group_name: str = ""        # e.g. "Blaster_Ranged"
    set_name: str = ""          # e.g. "Archery"
    static_index: int = 0       # used by MxDz qualified_names=False blocks
    level: int = 0
    power_type: int = 0
    available: int = 0
    desc_short: str = ""
    requires_classes: list = field(default_factory=list)
    group_membership: list = field(default_factory=list)  # mutex group names
    can_be_enhanced: bool = True   # False if power accepts no enhancement types


# ── SetType enum values ───────────────────────────────────────────────────

class SetType:
    NONE = 0
    PRIMARY = 1
    SECONDARY = 2
    ANCILLARY = 3
    INHERENT = 4
    POOL = 5
    SET_BONUS = 6
    TEMP = 7
    PET = 8
    ACCOLADE = 9
    INCARNATE = 10

    _names = {
        0: "None", 1: "Primary", 2: "Secondary", 3: "Ancillary",
        4: "Inherent", 5: "Pool", 6: "SetBonus", 7: "Temp",
        8: "Pet", 9: "Accolade", 10: "Incarnate",
    }

    @classmethod
    def name(cls, val):
        return cls._names.get(val, f"Unknown({val})")


# ── Parsing ───────────────────────────────────────────────────────────────

def read_archetype(reader: DotNetBinaryReader) -> Archetype:
    at = Archetype()
    at.display_name = reader.read_string()
    at.hitpoints = reader.read_int32()
    reader.read_single()          # HPCap
    reader.read_string()          # DescLong
    reader.read_single()          # ResCap
    origin_count = reader.read_int32() + 1
    for _ in range(origin_count):
        reader.read_string()      # Origin
    at.class_name = reader.read_string()
    at.class_type = reader.read_int32()
    reader.read_int32()           # Column
    at.desc_short = reader.read_string()
    at.primary_group = reader.read_string()
    at.secondary_group = reader.read_string()
    at.playable = reader.read_boolean()
    reader.read_single()          # RechargeCap
    reader.read_single()          # DamageCap
    reader.read_single()          # RecoveryCap
    reader.read_single()          # RegenCap
    reader.read_single()          # BaseRecovery
    reader.read_single()          # BaseRegen
    reader.read_single()          # BaseThreat
    reader.read_single()          # PerceptionCap
    return at


def read_powerset(reader: DotNetBinaryReader) -> PowersetInfo:
    ps = PowersetInfo()
    ps.display_name = reader.read_string()
    ps.n_archetype = reader.read_int32()
    ps.set_type = reader.read_int32()
    reader.read_string()          # ImageName
    ps.full_name = reader.read_string()
    if not ps.full_name:
        ps.full_name = f"Orphan.{ps.display_name.replace(' ', '_')}"
    ps.set_name = reader.read_string()
    ps.description = reader.read_string()
    reader.read_string()          # SubName
    ps.at_class = reader.read_string()
    reader.read_string()          # UIDTrunkSet
    reader.read_string()          # UIDLinkSecondary
    mutex_count = reader.read_int32() + 1
    for _ in range(mutex_count):
        reader.read_string()      # UIDMutexSet
        reader.read_int32()       # nIDMutexSet

    if '.' in ps.full_name:
        ps.group_name = ps.full_name[:ps.full_name.index('.')]
    return ps


def skip_requirement(reader: DotNetBinaryReader) -> list[str]:
    """Read a Requirement, return classname list, skip the rest."""
    class_count = reader.read_int32() + 1
    classes = [reader.read_string() for _ in range(class_count)]
    class_not_count = reader.read_int32() + 1
    for _ in range(class_not_count):
        reader.read_string()
    power_id_count = reader.read_int32() + 1
    for _ in range(power_id_count):
        reader.read_string()
        reader.read_string()
    power_id_not_count = reader.read_int32() + 1
    for _ in range(power_id_not_count):
        reader.read_string()
        reader.read_string()
    return classes


def read_power_header(reader: DotNetBinaryReader) -> PowerInfo:
    """
    Read a Power record, extracting key fields and skipping the bulk.
    Mirrors Power(BinaryReader) in Power.cs.
    """
    pw = PowerInfo()

    pw.static_index = reader.read_int32()
    pw.full_name = reader.read_string()
    pw.group_name = reader.read_string()
    pw.set_name = reader.read_string()
    pw.power_name = reader.read_string()
    pw.display_name = reader.read_string()
    pw.available = reader.read_int32()

    pw.requires_classes = skip_requirement(reader)

    reader.read_int32()           # ModesRequired
    reader.read_int32()           # ModesDisallowed
    pw.power_type = reader.read_int32()
    reader.read_single()          # Accuracy
    reader.read_int32()           # AttackTypes

    gm_count = reader.read_int32() + 1
    pw.group_membership = [s for s in (reader.read_string() for _ in range(gm_count)) if s]

    reader.read_int32()           # EntitiesAffected
    reader.read_int32()           # EntitiesAutoHit
    reader.read_int32()           # Target
    reader.read_boolean()         # TargetLoS
    reader.read_single()          # Range
    reader.read_int32()           # TargetSecondary
    reader.read_single()          # RangeSecondary
    reader.read_single()          # EndCost
    reader.read_single()          # InterruptTime
    reader.read_single()          # CastTime
    reader.read_single()          # RechargeTime
    reader.read_single()          # BaseRechargeTime
    reader.read_single()          # ActivatePeriod
    reader.read_int32()           # EffectArea
    reader.read_single()          # Radius
    reader.read_int32()           # Arc
    reader.read_int32()           # MaxTargets
    reader.read_string()          # MaxBoosts
    reader.read_int32()           # CastFlags
    reader.read_int32()           # AIReport
    reader.read_int32()           # NumCharges
    reader.read_int32()           # UsageTime
    reader.read_int32()           # LifeTime
    reader.read_int32()           # LifeTimeInGame
    reader.read_int32()           # NumAllowed
    reader.read_boolean()         # DoNotSave

    boosts_count = reader.read_int32() + 1
    for _ in range(boosts_count):
        reader.read_string()

    reader.read_boolean()         # CastThroughHold
    reader.read_boolean()         # IgnoreStrength
    pw.desc_short = reader.read_string()
    reader.read_string()          # DescLong

    enh_count = reader.read_int32() + 1
    pw.can_be_enhanced = enh_count > 0
    for _ in range(enh_count):
        reader.read_int32()

    set_type_count = reader.read_int32() + 1
    for _ in range(set_type_count):
        reader.read_int32()

    reader.read_boolean()         # ClickBuff
    reader.read_boolean()         # AlwaysToggle
    pw.level = reader.read_int32()
    reader.read_boolean()         # AllowFrontLoading
    reader.read_boolean()         # VariableEnabled
    reader.read_boolean()         # VariableOverride
    reader.read_string()          # VariableName
    reader.read_int32()           # VariableMin
    reader.read_int32()           # VariableMax

    subpower_count = reader.read_int32() + 1
    for _ in range(subpower_count):
        reader.read_string()

    ignore_enh_count = reader.read_int32() + 1
    for _ in range(ignore_enh_count):
        reader.read_int32()

    ignore_buff_count = reader.read_int32() + 1
    for _ in range(ignore_buff_count):
        reader.read_int32()

    reader.read_boolean()         # SkipMax
    reader.read_int32()           # InherentType
    reader.read_int32()           # DisplayLocation
    reader.read_boolean()         # MutexAuto
    reader.read_boolean()         # MutexIgnore
    reader.read_boolean()         # AbsorbSummonEffects
    reader.read_boolean()         # AbsorbSummonAttributes
    reader.read_boolean()         # ShowSummonAnyway
    reader.read_boolean()         # NeverAutoUpdate
    reader.read_boolean()         # NeverAutoUpdateRequirements
    reader.read_boolean()         # IncludeFlag
    reader.read_string()          # ForcedClass
    reader.read_boolean()         # SortOverride
    reader.read_boolean()         # BoostBoostable
    reader.read_boolean()         # BoostUsePlayerLevel

    effects_count = reader.read_int32() + 1
    for _ in range(effects_count):
        skip_effect(reader)

    reader.read_boolean()         # HiddenPower
    reader.read_boolean()         # Active
    reader.read_boolean()         # Taken
    reader.read_int32()           # Stacks
    reader.read_int32()           # VariableStart

    return pw


def parse_i12(filepath: str):
    """Parse I12.mhd, return archetypes, powersets, and powers."""
    data = Path(filepath).read_bytes()
    reader = DotNetBinaryReader(data)

    header = reader.read_string()
    if header != "Mids Reborn Powers Database":
        raise ValueError(f"Unexpected header: {header!r}")

    _version_str = reader.read_string()
    year = reader.read_int32()
    if year > 0:
        _month = reader.read_int32()
        _day = reader.read_int32()
    else:
        reader.read_bytes(8)      # DateTime as int64
    _issue = reader.read_int32()
    _page_vol = reader.read_int32()
    _page_vol_text = reader.read_string()

    at_header = reader.read_string()
    if at_header != "BEGIN:ARCHETYPES":
        raise ValueError(f"Expected ARCHETYPES header, got: {at_header!r}")
    at_count = reader.read_int32() + 1
    archetypes = []
    for i in range(at_count):
        at = read_archetype(reader)
        at.idx = i
        archetypes.append(at)

    ps_header = reader.read_string()
    if ps_header != "BEGIN:POWERSETS":
        raise ValueError(f"Expected POWERSETS header, got: {ps_header!r}")
    ps_count = reader.read_int32() + 1
    powersets = []
    for i in range(ps_count):
        try:
            ps = read_powerset(reader)
            ps.idx = i
            powersets.append(ps)
        except Exception as e:
            raise RuntimeError(
                f"Failed reading powerset {i}/{ps_count} at offset {reader.pos}: {e}"
            ) from e

    pw_header = reader.read_string()
    if pw_header != "BEGIN:POWERS":
        raise ValueError(f"Expected POWERS header, got: {pw_header!r}")
    pw_count = reader.read_int32() + 1
    powers = []
    for i in range(pw_count):
        try:
            pw = read_power_header(reader)
            powers.append(pw)
        except Exception as e:
            raise RuntimeError(
                f"Failed reading power {i}/{pw_count} at offset {reader.pos}: {e}"
            ) from e
        if (i + 1) % 500 == 0:
            print(f"  Read {i + 1}/{pw_count} powers...", file=sys.stderr)

    print(f"  Read {len(powers)}/{pw_count} powers total.", file=sys.stderr)

    return archetypes, powersets, powers


def build_class_powerset_tree(archetypes, powersets, powers):
    """
    Build a nested dict:
    {
        "Blaster": {
            "primary": {
                "Archery": {
                    "powers": ["Snap Shot", "Aimed Shot", ...],
                    "full_name": "Blaster_Ranged.Archery"
                }, ...
            },
            "secondary": { ... },
            "epic": { ... }
        }, ...
        "_pools": {
            "Flight": {
                "powers": ["Hover", "Fly", ...],
                "full_name": "Pool.Flight"
            }, ...
        }
    }
    """
    # Index powers by their powerset full name
    powers_by_set = {}
    for pw in powers:
        set_key = f"{pw.group_name}.{pw.set_name}"
        if set_key not in powers_by_set:
            powers_by_set[set_key] = []
        powers_by_set[set_key].append({
            "display_name": pw.display_name,
            "power_name": pw.power_name,
            "level": pw.level,
        })

    for set_key in powers_by_set:
        powers_by_set[set_key].sort(key=lambda p: p["level"])

    # Cache first power's requires_classes per powerset for epic matching
    first_power_classes = {}
    for pw in powers:
        set_key = f"{pw.group_name}.{pw.set_name}"
        if set_key not in first_power_classes and pw.requires_classes:
            first_power_classes[set_key] = pw.requires_classes

    tree = {}

    for at in archetypes:
        if not at.playable:
            continue

        entry = {"primary": {}, "secondary": {}, "epic": {}}

        for ps in powersets:
            set_powers = powers_by_set.get(ps.full_name, [])
            power_names = [p["display_name"] for p in set_powers]
            if not power_names:
                continue

            ps_entry = {
                "powers": power_names,
                "full_name": ps.full_name,
            }

            gn_upper = ps.group_name.upper()
            if gn_upper == at.primary_group.upper():
                entry["primary"][ps.display_name] = ps_entry
            elif gn_upper == at.secondary_group.upper():
                entry["secondary"][ps.display_name] = ps_entry
            elif gn_upper == "EPIC":
                if ps.at_class and ps.at_class.upper() == at.class_name.upper():
                    entry["epic"][ps.display_name] = ps_entry
                elif not ps.at_class:
                    req_classes = first_power_classes.get(ps.full_name, [])
                    if at.class_name in req_classes:
                        entry["epic"][ps.display_name] = ps_entry

        tree[at.display_name] = entry

    pool_sets = {}
    for ps in powersets:
        if ps.set_type == SetType.POOL:
            set_powers = powers_by_set.get(ps.full_name, [])
            if set_powers:
                pool_sets[ps.display_name] = {
                    "powers": [p["display_name"] for p in set_powers],
                    "full_name": ps.full_name,
                }
    tree["_pools"] = pool_sets

    return tree


def main():
    parser = argparse.ArgumentParser(
        description="Parse Mids Reborn I12.mhd and extract class/powerset/power mappings."
    )
    parser.add_argument("i12_path", help="Path to I12.mhd file")
    parser.add_argument("--json", metavar="FILE", help="Write full tree to JSON file")
    parser.add_argument(
        "--class", dest="show_class", metavar="NAME",
        help="Show powersets/powers for a specific class"
    )
    parser.add_argument(
        "--list-classes", action="store_true",
        help="Just list all playable classes"
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="Output a flat list: class|role|powerset|power"
    )
    args = parser.parse_args()

    print("Parsing database...", file=sys.stderr)
    archetypes, powersets, powers = parse_i12(args.i12_path)
    print(
        f"Loaded {len(archetypes)} archetypes, "
        f"{len(powersets)} powersets, {len(powers)} powers",
        file=sys.stderr,
    )

    tree = build_class_powerset_tree(archetypes, powersets, powers)

    if args.list_classes:
        for name in sorted(tree.keys()):
            if not name.startswith("_"):
                print(name)
        return

    if args.show_class:
        target = args.show_class
        match = None
        for name in tree:
            if name.lower() == target.lower():
                match = name
                break
        if not match:
            print(f"Class not found: {target}")
            print(f"Available: {', '.join(n for n in sorted(tree) if not n.startswith('_'))}")
            sys.exit(1)

        data = tree[match]
        print(f"\n=== {match} ===\n")
        for role in ("primary", "secondary", "epic"):
            sets = data.get(role, {})
            if not sets:
                continue
            print(f"  {role.upper()}:")
            for set_name, info in sorted(sets.items()):
                print(f"    {set_name}:")
                for pw in info["powers"]:
                    print(f"      - {pw}")
            print()

        print("  POOL POWERS:")
        for set_name, info in sorted(tree.get("_pools", {}).items()):
            print(f"    {set_name}:")
            for pw in info["powers"]:
                print(f"      - {pw}")
        return

    if args.flat:
        for class_name, data in sorted(tree.items()):
            if class_name.startswith("_"):
                continue
            for role in ("primary", "secondary", "epic"):
                for set_name, info in sorted(data.get(role, {}).items()):
                    for pw in info["powers"]:
                        print(f"{class_name}|{role}|{set_name}|{pw}")
        for set_name, info in sorted(tree.get("_pools", {}).items()):
            for pw in info["powers"]:
                print(f"_pool|pool|{set_name}|{pw}")
        return

    if args.json:
        Path(args.json).write_text(
            json.dumps(tree, indent=2, ensure_ascii=False)
        )
        print(f"Wrote tree to {args.json}", file=sys.stderr)
    else:
        for class_name, data in sorted(tree.items()):
            if class_name.startswith("_"):
                continue
            n_pri = len(data.get("primary", {}))
            n_sec = len(data.get("secondary", {}))
            n_epic = len(data.get("epic", {}))
            print(f"{class_name}: {n_pri} primary, {n_sec} secondary, {n_epic} epic")
        n_pools = len(tree.get("_pools", {}))
        print(f"\nPool powersets: {n_pools}")


if __name__ == "__main__":
    main()
