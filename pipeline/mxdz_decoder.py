"""
Decoder for the MxDz (legacy) build export format used by
Mids Hero Designer and Mids Reborn.

The MxDz format is a forum-pasteable text block containing:
  1. A header line like: |MxDz;1234;567;1134;HEX;|
  2. Hex-encoded (or UU-encoded), zlib-compressed binary data

The binary payload uses .NET BinaryWriter format and contains
character class, powersets, powers, and slotted enhancements,
stored as integer indices into the Mids powers/enhancement databases.

Usage:
    # With EnhDB.mhd for full enhancement resolution:
    python mxdz_decoder.py buildfile.txt --enhdb /path/to/EnhDB.mhd

    # Without database (enhancement slots shown as raw indices):
    python mxdz_decoder.py buildfile.txt

    # Output as JSON:
    python mxdz_decoder.py buildfile.txt --enhdb /path/to/EnhDB.mhd --json output.json

Requires enhdb_parser.py in the same directory (for DotNetBinaryReader).
"""

import re
import zlib
import json
import sys
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from .enhdb_parser import DotNetBinaryReader, parse_enhdb


# ── Outer decoding (text -> compressed bytes -> raw bytes) ────────────────

def uu_decode(data: bytes) -> bytes:
    """
    Decode Mids' UU-encoded bytes (4 input bytes -> 3 output bytes).
    Backtick (96) is treated as space (32).
    """
    out = bytearray()
    for i in range(0, len(data), 4):
        chunk = data[i:i+4]
        if len(chunk) < 4:
            # Pad with spaces if short
            chunk = chunk + bytes([32] * (4 - len(chunk)))
        b = [32 if x == 96 else x for x in chunk]
        out.append(((b[0] - 32) << 2 | (b[1] - 32) >> 4) & 0xFF)
        out.append((((b[1] - 32) & 0xF) << 4 | (b[2] - 32) >> 2) & 0xFF)
        out.append((((b[2] - 32) & 0x3) << 6 | (b[3] - 32)) & 0xFF)
    return bytes(out)


def hex_decode(data: bytes) -> bytes:
    """Decode hex-encoded bytes (ASCII hex string -> raw bytes)."""
    return bytes.fromhex(data.decode('ascii'))


def unbreak_hex(payload: str) -> str:
    """Strip everything except hex characters (0-9, A-F, a-f) from hex payload."""
    return ''.join(c for c in payload if c in '0123456789ABCDEFabcdef')


def unbreak_string(payload: str, bookend: bool = False) -> str:
    """Remove pipe bookends and newlines from payload."""
    if bookend:
        lines = payload.split('\n')
        lines = [line.strip('|').strip('\r') for line in lines]
        payload = ''.join(lines)
    else:
        payload = payload.replace('\r\n', '').replace('\n', '')
    return payload


def extract_mxdz(text: str) -> bytes:
    """
    Extract and decode the binary payload from an MxDz text block.
    Returns the decompressed raw bytes ready for binary parsing.
    """
    lines = text.replace('||', '|\n|').split('\n')

    # Find the header line containing MxDz or MxDu
    header_pattern = re.compile(r'\|?(MxD[zu]);(\d+);(\d+);(\d+);?(HEX)?;?\|?')
    header_match = None
    header_idx = -1

    for i, line in enumerate(lines):
        m = header_pattern.search(line)
        if m:
            header_match = m
            header_idx = i
            break

    if not header_match:
        raise ValueError("Could not find MxDz/MxDu header in input")

    magic = header_match.group(1)
    sz_uncompressed = int(header_match.group(2))
    sz_compressed = int(header_match.group(3))
    sz_encoded = int(header_match.group(4))
    is_hex = header_match.group(5) is not None

    # Payload is everything after the header line
    payload = '\n'.join(lines[header_idx + 1:])

    # Strip formatting
    if is_hex:
        cleaned = unbreak_hex(payload)
    else:
        cleaned = unbreak_string(payload, bookend=True)

    payload_bytes = cleaned.encode('ascii')

    # Truncate or check size
    if len(payload_bytes) < sz_encoded:
        print(
            f"Warning: payload is {len(payload_bytes)} bytes, "
            f"expected {sz_encoded}",
            file=sys.stderr,
        )
    elif len(payload_bytes) > sz_encoded:
        payload_bytes = payload_bytes[:sz_encoded]

    # Decode
    if is_hex:
        raw_bytes = hex_decode(payload_bytes)
    else:
        raw_bytes = uu_decode(payload_bytes)

    if len(raw_bytes) == 0:
        raise ValueError("Decoding produced empty result")

    # Decompress if MxDz (compressed)
    if magic == "MxDz":
        raw_bytes = zlib.decompress(raw_bytes)
        if len(raw_bytes) != sz_uncompressed:
            print(
                f"Warning: decompressed size {len(raw_bytes)}, "
                f"expected {sz_uncompressed}",
                file=sys.stderr,
            )

    return raw_bytes


# ── Enhancement type lookup ──────────────────────────────────────────────

# Enhancement types (mirrors Enums.eType)
TYPE_NONE = 0
TYPE_NORMAL = 1      # Note: in ReadSlotData, Normal uses ReadSByte x2
TYPE_SPECIAL = 2     # Same as Normal
TYPE_INVENT = 3      # IOLevel + RelativeLevel
TYPE_SET = 4         # Same as InventO

# Correction: looking at the C# enum and WriteSlotData more carefully:
# eType: None=0, Normal=1 (wrong - checking)
# Actually from the Enhancement class: TypeID is eType enum
# The WriteSlotData checks: Normal | SpecialO => 2 sbytes
#                           InventO | SetO => 2 sbytes
# So all non-None types read 2 extra bytes. The difference is what they mean.


@dataclass
class EnhLookup:
    """Lookup table for enhancement static_index -> type and name."""
    type_by_static_index: dict = field(default_factory=dict)
    uid_by_static_index: dict = field(default_factory=dict)
    name_by_static_index: dict = field(default_factory=dict)

    @classmethod
    def from_enhdb(cls, enhdb_path: str) -> 'EnhLookup':
        from .enhdb_parser import parse_enhdb, build_uid_to_display_name
        enhancements, enhancement_sets = parse_enhdb(enhdb_path)
        uid_to_display = build_uid_to_display_name(enhancements, enhancement_sets)

        lookup = cls()
        for enh in enhancements:
            lookup.type_by_static_index[enh.static_index] = enh.type_id
            lookup.uid_by_static_index[enh.static_index] = enh.uid
            lookup.name_by_static_index[enh.static_index] = uid_to_display.get(enh.uid, enh.name)
        return lookup

    @classmethod
    def from_refdata(cls, static_idx_to_uid: dict, uid_to_display: dict) -> 'EnhLookup':
        lookup = cls()
        for idx_str, uid in static_idx_to_uid.items():
            idx = int(idx_str)
            lookup.uid_by_static_index[idx] = uid
            lookup.name_by_static_index[idx] = uid_to_display.get(uid, uid)
        return lookup

    def get_type(self, static_index: int) -> int | None:
        return self.type_by_static_index.get(static_index)

    def get_name(self, static_index: int) -> str | None:
        return self.name_by_static_index.get(static_index)


# ── Binary payload parsing ───────────────────────────────────────────────

MAGIC_NUMBER = bytes([ord('M'), ord('x'), ord('D'), 12])

# Format version thresholds (from C# source)
VERSION_CURRENT = 3.20
VERSION_PRIOR = 3.10


@dataclass
class SlotInfo:
    level: int = 0
    is_inherent: bool = False
    enhancement_id: int = -1       # static index or -1
    enhancement_uid: str = ""      # UID if qualifiedNames, else resolved from DB
    enhancement_name: str = ""     # display name if resolved
    relative_level: int = 0
    grade: int = 0
    io_level: int = 0
    enh_type: str = ""             # "Normal", "Special", "Invention", "Set", "None"
    # Flipped enhancement (alternate)
    has_flipped: bool = False
    flipped_enhancement_id: int = -1
    flipped_enhancement_uid: str = ""
    flipped_enhancement_name: str = ""


@dataclass
class SubPowerInfo:
    power_id: int = -1           # static index
    power_name: str = ""         # qualified name if available
    stat_include: bool = False


@dataclass
class PowerEntryInfo:
    power_id: int = -1           # static index or -1
    power_name: str = ""         # qualified name if qualifiedNames
    level: int = 0
    stat_include: bool = False
    proc_include: bool = False
    variable_value: int = 0
    inherent_slots_used: int = 0
    sub_powers: list = field(default_factory=list)
    slots: list = field(default_factory=list)


@dataclass
class MxDzBuild:
    format_version: float = 0.0
    qualified_names: bool = False
    has_sub_powers: bool = False
    class_uid: str = ""
    origin: str = ""
    alignment: int = 0
    character_name: str = ""
    powersets: list = field(default_factory=list)
    last_power: int = 0
    powers: list = field(default_factory=list)


def _enh_type_name(type_id: int) -> str:
    return {0: "None", 1: "Normal", 2: "Special", 3: "Invention", 4: "Set"}.get(type_id, f"Unknown({type_id})")


def read_slot_data(
    reader: DotNetBinaryReader,
    qualified_names: bool,
    version: float,
    enh_lookup: EnhLookup | None,
) -> SlotInfo:
    """Read enhancement slot data. Mirrors ReadSlotData in C#."""
    slot = SlotInfo()

    if qualified_names:
        uid = reader.read_string()
        slot.enhancement_uid = uid
        if uid:
            slot.enhancement_id = 0  # placeholder, we have the name
            slot.enhancement_name = uid
        else:
            slot.enhancement_id = -1
            return slot
    else:
        static_idx = reader.read_int32()
        slot.enhancement_id = static_idx
        if static_idx < 0:
            return slot
        if enh_lookup:
            slot.enhancement_uid = enh_lookup.uid_by_static_index.get(static_idx, "")
            slot.enhancement_name = enh_lookup.get_name(static_idx) or f"[index:{static_idx}]"

    # Determine enhancement type to know how many extra bytes to read
    enh_type = None
    if qualified_names:
        # With qualified names, the reader in C# looks up the type from the DB
        # We can try to match the UID against our lookup if available
        if enh_lookup and slot.enhancement_uid:
            for sid, uid in enh_lookup.uid_by_static_index.items():
                if uid == slot.enhancement_uid:
                    enh_type = enh_lookup.get_type(sid)
                    break
    else:
        if enh_lookup:
            enh_type = enh_lookup.get_type(slot.enhancement_id)

    if enh_type is None:
        # Can't determine type — we have to guess.
        # The current writer always writes 2 sbytes for any non-empty slot,
        # so we'll assume 2 bytes.
        slot.enh_type = "Unknown"
        slot.relative_level = reader.read_bytes(1)[0]
        slot.grade = reader.read_bytes(1)[0]
        return slot

    slot.enh_type = _enh_type_name(enh_type)

    if enh_type in (1, 2):  # Normal, SpecialO
        slot.relative_level = int.from_bytes(reader.read_bytes(1), 'little', signed=True)
        slot.grade = int.from_bytes(reader.read_bytes(1), 'little', signed=True)
    elif enh_type in (3, 4):  # InventO, SetO
        slot.io_level = int.from_bytes(reader.read_bytes(1), 'little', signed=True)
        if slot.io_level > 49:
            slot.io_level = 49
        if version > 1.0:
            slot.relative_level = int.from_bytes(reader.read_bytes(1), 'little', signed=True)
    # enh_type 0 (None) reads nothing extra

    return slot


def parse_mxdz_binary(
    data: bytes,
    enh_lookup: EnhLookup | None = None,
) -> MxDzBuild:
    """Parse the decompressed MxDz binary payload."""
    reader = DotNetBinaryReader(data)
    build = MxDzBuild()

    # Scan for magic number
    found = False
    magic_len = len(MAGIC_NUMBER)
    for offset in range(min(len(data) - magic_len, 20)):
        if data[offset:offset+magic_len] == MAGIC_NUMBER:
            reader.pos = offset + magic_len
            found = True
            break

    if not found:
        raise ValueError(
            f"Magic number not found. First 20 bytes: {data[:20].hex()}"
        )

    build.format_version = reader.read_single()
    version = build.format_version

    if version > VERSION_CURRENT + 0.001:
        print(
            f"Warning: format version {version} is newer than "
            f"expected {VERSION_CURRENT}",
            file=sys.stderr,
        )

    # Determine format era
    if version < VERSION_PRIOR:
        format_era = "Legacy"
    elif version < VERSION_CURRENT:
        format_era = "Prior"
    else:
        format_era = "Current"

    build.qualified_names = reader.read_boolean()
    build.has_sub_powers = reader.read_boolean()

    build.class_uid = reader.read_string()
    build.origin = reader.read_string()

    if version > 1:
        build.alignment = reader.read_int32()

    build.character_name = reader.read_string()

    # Powersets
    ps_count = reader.read_int32() + 1
    build.powersets = [reader.read_string() for _ in range(ps_count)]

    build.last_power = reader.read_int32() - 1

    # Powers
    power_count = reader.read_int32() + 1
    for pi in range(power_count):
        pe = PowerEntryInfo()

        if build.qualified_names:
            name = reader.read_string()
            pe.power_name = name
            pe.power_id = 0 if name else -1
        else:
            pe.power_id = reader.read_int32()

        # If power_id is valid (or name is non-empty), read power metadata
        has_power = (
            (build.qualified_names and pe.power_name)
            or (not build.qualified_names and pe.power_id > -1)
        )

        if has_power:
            pe.level = int.from_bytes(reader.read_bytes(1), 'little', signed=True)

            if format_era == "Current":
                pe.stat_include = reader.read_boolean()
                pe.proc_include = reader.read_boolean()
                pe.variable_value = reader.read_int32()
                pe.inherent_slots_used = reader.read_int32()
            elif format_era == "Prior":
                pe.stat_include = reader.read_boolean()
                pe.proc_include = reader.read_boolean()
                pe.variable_value = reader.read_int32()
            else:  # Legacy
                pe.stat_include = reader.read_boolean()
                pe.variable_value = reader.read_int32()

            # Sub-powers
            if build.has_sub_powers:
                sp_count = int.from_bytes(reader.read_bytes(1), 'little', signed=True) + 1
                for _ in range(sp_count):
                    sp = SubPowerInfo()
                    if build.qualified_names:
                        sp.power_name = reader.read_string()
                    else:
                        sp.power_id = reader.read_int32()
                    sp.stat_include = reader.read_boolean()
                    pe.sub_powers.append(sp)

        # Slots (always present, even for empty power entries)
        slot_count = int.from_bytes(reader.read_bytes(1), 'little', signed=True) + 1
        for _ in range(slot_count):
            slot = SlotInfo()
            slot.level = int.from_bytes(reader.read_bytes(1), 'little', signed=True)
            if format_era == "Current":
                slot.is_inherent = reader.read_boolean()

            # Primary enhancement
            slot_data = read_slot_data(reader, build.qualified_names, version, enh_lookup)
            slot.enhancement_id = slot_data.enhancement_id
            slot.enhancement_uid = slot_data.enhancement_uid
            slot.enhancement_name = slot_data.enhancement_name
            slot.relative_level = slot_data.relative_level
            slot.grade = slot_data.grade
            slot.io_level = slot_data.io_level
            slot.enh_type = slot_data.enh_type

            # Flipped (alternate) enhancement
            has_flipped = reader.read_boolean()
            slot.has_flipped = has_flipped
            if has_flipped:
                flip_data = read_slot_data(reader, build.qualified_names, version, enh_lookup)
                slot.flipped_enhancement_id = flip_data.enhancement_id
                slot.flipped_enhancement_uid = flip_data.enhancement_uid
                slot.flipped_enhancement_name = flip_data.enhancement_name

            pe.slots.append(slot)

        build.powers.append(pe)

    return build


# ── Output formatting ────────────────────────────────────────────────────

def build_to_dict(build: MxDzBuild) -> dict:
    """Convert build to a JSON-serializable dict."""
    powers = []
    for pe in build.powers:
        if pe.power_id < 0 and not pe.power_name:
            # Empty power slot
            power_dict = {"power_id": -1, "slots": []}
        else:
            power_dict = {
                "level": pe.level,
                "stat_include": pe.stat_include,
            }
            if build.qualified_names:
                power_dict["power_name"] = pe.power_name
            else:
                power_dict["power_static_index"] = pe.power_id

            if pe.proc_include:
                power_dict["proc_include"] = True
            if pe.variable_value:
                power_dict["variable_value"] = pe.variable_value
            if pe.inherent_slots_used:
                power_dict["inherent_slots_used"] = pe.inherent_slots_used

            if pe.sub_powers:
                subs = []
                for sp in pe.sub_powers:
                    sub_dict = {"stat_include": sp.stat_include}
                    if build.qualified_names:
                        sub_dict["power_name"] = sp.power_name
                    else:
                        sub_dict["power_static_index"] = sp.power_id
                    subs.append(sub_dict)
                power_dict["sub_powers"] = subs

        slots = []
        for s in pe.slots:
            slot_dict = {"level": s.level}
            if s.is_inherent:
                slot_dict["is_inherent"] = True
            if s.enhancement_id >= 0 or s.enhancement_uid:
                enh = {}
                if s.enhancement_name:
                    enh["name"] = s.enhancement_name
                if s.enhancement_uid:
                    enh["uid"] = s.enhancement_uid
                elif s.enhancement_id >= 0:
                    enh["static_index"] = s.enhancement_id
                if s.enh_type:
                    enh["type"] = s.enh_type
                if s.io_level:
                    enh["io_level"] = s.io_level
                slot_dict["enhancement"] = enh
            if s.has_flipped and (s.flipped_enhancement_id >= 0 or s.flipped_enhancement_uid):
                flip = {}
                if s.flipped_enhancement_name:
                    flip["name"] = s.flipped_enhancement_name
                if s.flipped_enhancement_uid:
                    flip["uid"] = s.flipped_enhancement_uid
                elif s.flipped_enhancement_id >= 0:
                    flip["static_index"] = s.flipped_enhancement_id
                slot_dict["flipped_enhancement"] = flip
            slots.append(slot_dict)
        power_dict["slots"] = slots
        powers.append(power_dict)

    return {
        "format_version": build.format_version,
        "qualified_names": build.qualified_names,
        "class": build.class_uid,
        "origin": build.origin,
        "alignment": build.alignment,
        "name": build.character_name,
        "powersets": build.powersets,
        "powers": powers,
    }


def print_build_summary(build: MxDzBuild):
    """Print a human-readable summary of the build."""
    alignment_names = {0: "Hero", 1: "Villain", 2: "Rogue", 3: "Vigilante"}
    print(f"Character: {build.character_name or '(unnamed)'}")
    print(f"Class: {build.class_uid}")
    print(f"Origin: {build.origin}")
    print(f"Alignment: {alignment_names.get(build.alignment, str(build.alignment))}")
    print(f"Format version: {build.format_version}")
    print(f"Qualified names: {build.qualified_names}")
    print()

    print("Powersets:")
    for ps in build.powersets:
        if ps:
            print(f"  {ps}")
    print()

    print("Powers:")
    for i, pe in enumerate(build.powers):
        if pe.power_id < 0 and not pe.power_name:
            continue
        name = pe.power_name if pe.power_name else f"[static_index:{pe.power_id}]"
        print(f"  [{pe.level:2d}] {name}")
        for s in pe.slots:
            if s.enhancement_id >= 0 or s.enhancement_uid:
                enh_str = s.enhancement_name or s.enhancement_uid or f"[index:{s.enhancement_id}]"
                level_str = ""
                if s.io_level:
                    level_str = f" (IO level {s.io_level + 1})"
                elif s.grade:
                    grade_names = {0: "", 1: "Training", 2: "Dual Origin", 3: "Single Origin"}
                    level_str = f" ({grade_names.get(s.grade, '')})"
                print(f"       slot [{s.level:2d}]: {enh_str}{level_str}")
            else:
                print(f"       slot [{s.level:2d}]: (empty)")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Decode MxDz (legacy Mids) build export format."
    )
    parser.add_argument(
        "input",
        help="Path to text file containing the MxDz block, or '-' for stdin"
    )
    parser.add_argument(
        "--enhdb", metavar="PATH",
        help="Path to EnhDB.mhd for enhancement name resolution"
    )
    parser.add_argument(
        "--json", metavar="FILE",
        help="Write decoded build to JSON file"
    )
    parser.add_argument(
        "--raw-hex", action="store_true",
        help="Dump the decompressed binary as hex (for debugging)"
    )
    args = parser.parse_args()

    # Read input
    if args.input == '-':
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(errors='replace')

    # Load enhancement database if provided
    enh_lookup = None
    if args.enhdb:
        print("Loading enhancement database...", file=sys.stderr)
        enh_lookup = EnhLookup.from_enhdb(args.enhdb)
        print(
            f"Loaded {len(enh_lookup.type_by_static_index)} enhancements",
            file=sys.stderr,
        )

    # Extract and decompress
    print("Extracting payload...", file=sys.stderr)
    raw_bytes = extract_mxdz(text)

    if args.raw_hex:
        for i in range(0, len(raw_bytes), 16):
            hex_str = ' '.join(f'{b:02x}' for b in raw_bytes[i:i+16])
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw_bytes[i:i+16])
            print(f'  {i:04x}: {hex_str:<48} {ascii_str}')
        return

    # Parse binary
    print("Parsing build data...", file=sys.stderr)
    try:
        build = parse_mxdz_binary(raw_bytes, enh_lookup)
    except Exception as e:
        print(f"Parse failed: {e}", file=sys.stderr)
        print(f"Try --raw-hex to inspect the binary data", file=sys.stderr)
        sys.exit(1)

    if args.json:
        result = build_to_dict(build)
        Path(args.json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False)
        )
        print(f"Wrote decoded build to {args.json}", file=sys.stderr)
    else:
        print_build_summary(build)


if __name__ == "__main__":
    main()
