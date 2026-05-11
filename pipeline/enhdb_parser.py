"""
Parser for Mids Reborn EnhDB.mhd binary database file.

Extracts the mapping between internal enhancement UIDs
(e.g. 'Crafted_Luck_of_the_Gambler_D') and their display names
(e.g. 'Luck of the Gambler: Defense/Endurance/Recharge').

The binary format uses .NET BinaryWriter conventions:
  - Strings are length-prefixed (7-bit encoded length, then UTF-8 bytes)
  - Integers are little-endian int32
  - Floats are little-endian single (4 bytes)
  - Booleans are single bytes

Usage:
    python enhdb_parser.py /path/to/EnhDB.mhd
    python enhdb_parser.py /path/to/EnhDB.mhd --json output.json
    python enhdb_parser.py /path/to/EnhDB.mhd --csv output.csv

    Dump the full abbreviation -> display name mapping to JSON
    python enhdb_parser.py /path/to/EnhDB.mhd --abbrev abbrevs.json

    Quick lookup of a single abbreviation
    python enhdb_parser.py /path/to/EnhDB.mhd --lookup-abbrev "PrfShf-End%"

    The abbreviation mapping covers set enhancements (which make up the bulk of what you see in build exports), plus generic IOs and basic enhancements keyed by their ShortName alone.

"""

import struct
import json
import csv
import sys
import argparse
from dataclasses import dataclass, field
from pathlib import Path


# ── .NET BinaryReader primitives ──────────────────────────────────────────

class DotNetBinaryReader:
    """Reads .NET BinaryWriter-formatted data from a byte buffer."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_bytes(self, n: int) -> bytes:
        result = self.data[self.pos:self.pos + n]
        if len(result) < n:
            raise EOFError(f"Expected {n} bytes at offset {self.pos}, got {len(result)}")
        self.pos += n
        return result

    def read_int32(self) -> int:
        return struct.unpack('<i', self.read_bytes(4))[0]

    def read_single(self) -> float:
        return struct.unpack('<f', self.read_bytes(4))[0]

    def read_boolean(self) -> bool:
        return self.read_bytes(1)[0] != 0

    def read_string(self) -> str:
        """Read a .NET length-prefixed string (7-bit encoded length)."""
        length = self._read_7bit_encoded_int()
        raw = self.read_bytes(length)
        return raw.decode('utf-8')

    def _read_7bit_encoded_int(self) -> int:
        """Read a variable-length integer in .NET's 7-bit encoding."""
        result = 0
        shift = 0
        while True:
            byte = self.read_bytes(1)[0]
            result |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift >= 35:
                raise ValueError("Malformed 7-bit encoded integer")
        return result


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class Enhancement:
    static_index: int = 0
    name: str = ""           # e.g. "Defense/Endurance/Recharge"
    short_name: str = ""
    desc: str = ""
    type_id: int = 0         # 1=Normal, 2=SpecialO, 3=InventO, 4=SetO
    sub_type_id: int = 0
    class_ids: list = field(default_factory=list)
    image: str = ""
    set_index: int = -1      # nIDSet - index into EnhancementSets array
    uid_set: str = ""        # UIDSet
    effect_chance: float = 1.0
    level_min: int = 0
    level_max: int = 52
    unique: bool = False
    mut_ex_id: int = 0
    buff_mode: int = 0
    uid: str = ""            # e.g. "Crafted_Luck_of_the_Gambler_D"
    recipe_name: str = ""
    superior: bool = False
    is_proc: bool = False
    is_scalable: bool = False


@dataclass
class EnhancementSet:
    display_name: str = ""   # e.g. "Luck of the Gambler"
    short_name: str = ""
    uid: str = ""
    desc: str = ""
    set_type: int = 0
    image: str = ""
    level_min: int = 0
    level_max: int = 52
    enhancement_indices: list = field(default_factory=list)


# ── Parsing functions ─────────────────────────────────────────────────────

def skip_effect(reader: DotNetBinaryReader):
    """
    Read through an Effect record to advance the file pointer,
    discarding the data. Mirrors Effect(BinaryReader) constructor
    in Effect.cs.
    """
    reader.read_string()    # PowerFullName
    reader.read_int32()     # UniqueID
    reader.read_int32()     # EffectClass
    reader.read_int32()     # EffectType
    reader.read_int32()     # DamageType
    reader.read_int32()     # MezType
    reader.read_int32()     # ETModifies
    reader.read_string()    # Summon
    reader.read_single()    # DelayedTime
    reader.read_int32()     # Ticks
    reader.read_int32()     # Stacking
    reader.read_single()    # BaseProbability
    reader.read_int32()     # Suppression
    reader.read_boolean()   # Buffable
    reader.read_boolean()   # Resistible
    reader.read_int32()     # SpecialCase
    reader.read_boolean()   # VariableModifiedOverride
    reader.read_boolean()   # IgnoreScaling
    reader.read_int32()     # PvMode
    reader.read_int32()     # ToWho
    reader.read_int32()     # DisplayPercentageOverride
    reader.read_single()    # Scale
    reader.read_single()    # nMagnitude
    reader.read_single()    # nDuration
    reader.read_int32()     # AttribType
    reader.read_int32()     # Aspect
    reader.read_string()    # ModifierTable
    reader.read_boolean()   # NearGround
    reader.read_boolean()   # CancelOnMiss
    reader.read_boolean()   # RequiresToHitCheck
    reader.read_string()    # UIDClassName
    reader.read_int32()     # nIDClassName
    # Expressions
    reader.read_string()    # Duration
    reader.read_string()    # Magnitude
    reader.read_string()    # Probability
    reader.read_string()    # Reward
    reader.read_string()    # EffectId
    reader.read_boolean()   # IgnoreED
    reader.read_string()    # Override
    reader.read_single()    # ProcsPerMinute
    reader.read_int32()     # PowerAttribs
    # AtrOrig fields (6 floats, 2 ints, 1 enum stored as int)
    reader.read_single()    # AtrOrigAccuracy
    reader.read_single()    # AtrOrigActivatePeriod
    reader.read_int32()     # AtrOrigArc
    reader.read_single()    # AtrOrigCastTime
    reader.read_int32()     # AtrOrigEffectArea (enum)
    reader.read_single()    # AtrOrigEnduranceCost
    reader.read_single()    # AtrOrigInterruptTime
    reader.read_int32()     # AtrOrigMaxTargets
    reader.read_single()    # AtrOrigRadius
    reader.read_single()    # AtrOrigRange
    reader.read_single()    # AtrOrigRechargeTime
    reader.read_single()    # AtrOrigSecondaryRange
    # AtrMod fields (same layout)
    reader.read_single()    # AtrModAccuracy
    reader.read_single()    # AtrModActivatePeriod
    reader.read_int32()     # AtrModArc
    reader.read_single()    # AtrModCastTime
    reader.read_int32()     # AtrModEffectArea (enum)
    reader.read_single()    # AtrModEnduranceCost
    reader.read_single()    # AtrModInterruptTime
    reader.read_int32()     # AtrModMaxTargets
    reader.read_single()    # AtrModRadius
    reader.read_single()    # AtrModRange
    reader.read_single()    # AtrModRechargeTime
    reader.read_single()    # AtrModSecondaryRange
    # ActiveConditionals
    conditional_count = reader.read_int32()
    for _ in range(conditional_count):
        reader.read_string()  # key
        reader.read_string()  # value


def read_enhancement(reader: DotNetBinaryReader) -> Enhancement:
    """Read a single Enhancement record. Mirrors Enhancement(BinaryReader)."""
    enh = Enhancement()
    enh.static_index = reader.read_int32()
    enh.name = reader.read_string()
    enh.short_name = reader.read_string()
    enh.desc = reader.read_string()
    enh.type_id = reader.read_int32()
    enh.sub_type_id = reader.read_int32()

    class_count = reader.read_int32() + 1
    enh.class_ids = [reader.read_int32() for _ in range(class_count)]

    enh.image = reader.read_string()
    enh.set_index = reader.read_int32()
    enh.uid_set = reader.read_string()
    enh.effect_chance = reader.read_single()
    enh.level_min = reader.read_int32()
    enh.level_max = reader.read_int32()
    enh.unique = reader.read_boolean()
    enh.mut_ex_id = reader.read_int32()
    enh.buff_mode = reader.read_int32()

    # Effects array — read through but don't store
    effect_count = reader.read_int32() + 1
    for _ in range(effect_count):
        # Each effect: Mode, BuffMode, Enhance.ID, Enhance.SubID, Schedule, Multiplier
        reader.read_int32()   # Mode
        reader.read_int32()   # BuffMode
        reader.read_int32()   # Enhance.ID
        reader.read_int32()   # Enhance.SubID
        reader.read_int32()   # Schedule
        reader.read_single()  # Multiplier
        # Optional nested Effect object
        has_fx = reader.read_boolean()
        if has_fx:
            skip_effect(reader)

    enh.uid = reader.read_string()
    enh.recipe_name = reader.read_string()
    enh.superior = reader.read_boolean()
    enh.is_proc = reader.read_boolean()
    enh.is_scalable = reader.read_boolean()

    return enh


def read_enhancement_set(reader: DotNetBinaryReader) -> EnhancementSet:
    """Read a single EnhancementSet record. Mirrors EnhancementSet(BinaryReader)."""
    es = EnhancementSet()
    es.display_name = reader.read_string()
    es.short_name = reader.read_string()
    es.uid = reader.read_string()
    es.desc = reader.read_string()
    es.set_type = reader.read_int32()
    es.image = reader.read_string()
    es.level_min = reader.read_int32()
    es.level_max = reader.read_int32()

    enh_count = reader.read_int32() + 1
    es.enhancement_indices = [reader.read_int32() for _ in range(enh_count)]

    # Bonus array
    bonus_count = reader.read_int32() + 1
    for _ in range(bonus_count):
        reader.read_int32()     # Special
        reader.read_string()    # AltString
        reader.read_int32()     # PvMode
        reader.read_int32()     # Slotted
        name_count = reader.read_int32() + 1
        for _ in range(name_count):
            reader.read_string()  # Name
            reader.read_int32()   # Index

    # SpecialBonus array
    special_count = reader.read_int32() + 1
    for _ in range(special_count):
        reader.read_int32()     # Special
        reader.read_string()    # AltString
        name_count = reader.read_int32() + 1
        for _ in range(name_count):
            reader.read_string()  # Name
            reader.read_int32()   # Index

    return es


def parse_enhdb(filepath: str) -> tuple[list[Enhancement], list[EnhancementSet]]:
    """
    Parse an EnhDB.mhd file and return lists of enhancements and sets.
    """
    data = Path(filepath).read_bytes()
    reader = DotNetBinaryReader(data)

    # File header
    header = reader.read_string()
    if header != "Mids Reborn Enhancement Database":
        raise ValueError(f"Unexpected header: {header!r}")

    version = reader.read_single()  # version float, ignored

    # Enhancements
    enh_count = reader.read_int32() + 1
    enhancements = []
    for i in range(enh_count):
        try:
            enhancements.append(read_enhancement(reader))
        except Exception as e:
            raise RuntimeError(
                f"Failed reading enhancement {i}/{enh_count} at offset {reader.pos}: {e}"
            ) from e

    # Enhancement Sets
    set_count = reader.read_int32() + 1
    enhancement_sets = []
    for i in range(set_count):
        try:
            enhancement_sets.append(read_enhancement_set(reader))
        except Exception as e:
            raise RuntimeError(
                f"Failed reading enhancement set {i}/{set_count} at offset {reader.pos}: {e}"
            ) from e

    return enhancements, enhancement_sets


def build_uid_to_display_name(
    enhancements: list[Enhancement],
    enhancement_sets: list[EnhancementSet],
) -> dict[str, str]:
    """
    Build the mapping from enhancement UID to full display name.

    For set enhancements (type_id == 4):
        "{SetDisplayName}: {EnhancementName}"
        e.g. "Luck of the Gambler: Defense/Endurance/Recharge"

    For invention enhancements (type_id == 3):
        "Invention: {Name}"

    For others:
        Just the Name.
    """
    # Type IDs as stored in EnhDB.mhd (matches Enums.eType in C# source).
    TYPE_NORMAL = 1
    TYPE_SPECIAL = 2
    TYPE_INVENT = 3
    TYPE_SET = 4

    mapping = {}
    for enh in enhancements:
        if not enh.uid:
            continue

        if enh.type_id == TYPE_SET and 0 <= enh.set_index < len(enhancement_sets):
            set_name = enhancement_sets[enh.set_index].display_name
            display = f"{set_name}: {enh.name}"
        elif enh.type_id == TYPE_INVENT:
            display = f"Invention: {enh.name}"
        else:
            display = enh.name

        mapping[enh.uid] = display

    return mapping


def build_abbrev_to_display_name(
    enhancements: list[Enhancement],
    enhancement_sets: list[EnhancementSet],
) -> dict[str, str]:
    """
    Build the mapping from short abbreviation to full display name.

    The abbreviation format used in Mids' plain text export is:
        "{SetShortName}-{EnhancementShortName}"
        e.g. "PrfShf-End%" => "Performance Shifter: Chance for +Endurance"
             "LucoftheG-Def/Rchg+" => "Luck of the Gambler: Defense/Increased Recharge"
             "Obl-%Dam" => "Obliteration: Chance for Smashing Damage"

    For non-set enhancements (generic IOs, Training, etc.), the abbreviation
    is just the ShortName with no set prefix:
        e.g. "RechRdx-I" (Recharge Reduction IO), "EndRdx-I" (Endurance Reduction IO)
    These are included with a "type" field in the full output but don't have
    a set prefix to form the abbreviation, so they're keyed by ShortName alone.
    """
    # Type IDs as stored in EnhDB.mhd (matches Enums.eType in C# source).
    TYPE_NORMAL = 1
    TYPE_SPECIAL = 2
    TYPE_INVENT = 3
    TYPE_SET = 4

    mapping = {}
    for enh in enhancements:
        if not enh.short_name:
            continue

        if enh.type_id == TYPE_SET and 0 <= enh.set_index < len(enhancement_sets):
            es = enhancement_sets[enh.set_index]
            abbrev = f"{es.short_name}-{enh.short_name}"
            display = f"{es.display_name}: {enh.name}"
            mapping[abbrev] = display
        elif enh.type_id == TYPE_INVENT:
            # Generic Invention enhancements like "EndRdx-I"
            # ShortName is the full abbreviation here
            mapping[enh.short_name] = f"Invention: {enh.name}"
        elif enh.type_id in (TYPE_NORMAL, TYPE_SPECIAL):
            mapping[enh.short_name] = enh.name

    return mapping


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parse Mids Reborn EnhDB.mhd and extract enhancement name mappings."
    )
    parser.add_argument("enhdb_path", help="Path to EnhDB.mhd file")
    parser.add_argument("--json", metavar="FILE", help="Write UID mapping to JSON file")
    parser.add_argument("--csv", metavar="FILE", help="Write UID mapping to CSV file")
    parser.add_argument("--abbrev", metavar="FILE",
                        help="Write abbreviation -> display name mapping to JSON file")
    parser.add_argument("--lookup", metavar="UID", help="Look up a single UID")
    parser.add_argument("--lookup-abbrev", metavar="ABBREV",
                        help="Look up a single abbreviation (e.g. PrfShf-End%%)")
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print stats about what was parsed"
    )
    args = parser.parse_args()

    enhancements, enhancement_sets = parse_enhdb(args.enhdb_path)
    mapping = build_uid_to_display_name(enhancements, enhancement_sets)

    if args.verbose:
        print(f"Parsed {len(enhancements)} enhancements, {len(enhancement_sets)} sets")
        print(f"Built {len(mapping)} UID -> display name mappings")
        from collections import Counter
        types = Counter(e.type_id for e in enhancements)
        type_names = {1: "Normal", 2: "Special", 3: "Invention", 4: "Set"}
        for t, count in sorted(types.items()):
            print(f"  {type_names.get(t, f'Unknown({t})')}: {count}")

    if args.lookup:
        result = mapping.get(args.lookup)
        if result:
            print(f"{args.lookup} => {result}")
        else:
            for uid, name in mapping.items():
                if uid.lower() == args.lookup.lower():
                    print(f"{uid} => {name}")
                    break
            else:
                print(f"UID not found: {args.lookup}")
                sys.exit(1)

    if args.lookup_abbrev:
        abbrev_mapping = build_abbrev_to_display_name(enhancements, enhancement_sets)
        target = args.lookup_abbrev
        result = abbrev_mapping.get(target)
        if result:
            print(f"{target} => {result}")
        else:
            for abbr, name in abbrev_mapping.items():
                if abbr.lower() == target.lower():
                    print(f"{abbr} => {name}")
                    break
            else:
                print(f"Abbreviation not found: {target}")
                sys.exit(1)

    if args.json:
        Path(args.json).write_text(json.dumps(mapping, indent=2, ensure_ascii=False))
        print(f"Wrote {len(mapping)} entries to {args.json}")

    if args.abbrev:
        abbrev_mapping = build_abbrev_to_display_name(enhancements, enhancement_sets)
        Path(args.abbrev).write_text(
            json.dumps(abbrev_mapping, indent=2, ensure_ascii=False)
        )
        print(f"Wrote {len(abbrev_mapping)} entries to {args.abbrev}")

    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["uid", "display_name"])
            for uid, name in sorted(mapping.items()):
                writer.writerow([uid, name])
        print(f"Wrote {len(mapping)} entries to {args.csv}")

    # If no specific output requested, print some examples
    if not args.json and not args.csv and not args.lookup and not args.abbrev and not args.lookup_abbrev:
        print(f"Parsed {len(enhancements)} enhancements, {len(enhancement_sets)} sets")
        print(f"\nSample set enhancement mappings:")
        count = 0
        for uid, name in mapping.items():
            enh = next((e for e in enhancements if e.uid == uid), None)
            if enh and enh.type_id == 4:
                print(f"  {uid}  =>  {name}")
                count += 1
                if count >= 15:
                    print(f"  ... and {sum(1 for e in enhancements if e.type_id == 4) - 15} more")
                    break


if __name__ == "__main__":
    main()
