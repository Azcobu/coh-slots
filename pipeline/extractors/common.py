"""
Shared types and helpers for build extractors.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html import unescape


@dataclass
class SlotEnh:
    """A single enhancement in a slot. Only tracked kinds (set/io) are kept."""
    uid: str | None = None         # canonical UID; may be None if unresolved
    display: str | None = None     # 'Set: Name' or 'Invention: Name'
    set_name: str | None = None    # NULL for generic IOs
    kind: str = ""                 # 'set' | 'io'
    io_level: int | None = None


@dataclass
class PowerSlotting:
    """One taken power and the enhancements slotted into it."""
    power_full_name: str           # canonical, e.g. Blaster_Ranged.Archery.Snap_Shot
    enhancements: list[SlotEnh] = field(default_factory=list)


@dataclass
class BuildRecord:
    post_id: int
    block_index: int = 0
    source_format: str = ""        # 'MBD' | 'MxDz' | 'text'
    archetype: str | None = None   # canonical AT display name
    primary_set: str | None = None # display name
    secondary_set: str | None = None
    epic_set: str | None = None
    powers: list[PowerSlotting] = field(default_factory=list)
    parsed_partial: bool = False

    def signature(self) -> str:
        """
        Stable hash used for cross-author dedup.
        Built from (class, primary, secondary, sorted [(power, sorted enh tuple)]).
        Empty/unresolved enhancements are kept (UID 'unknown:...') so two
        builds that differ only in unresolved IOs still differ.
        """
        items = []
        for p in self.powers:
            enh_keys = sorted(
                (e.uid or e.display or "?") for e in p.enhancements
            )
            items.append((p.power_full_name, tuple(enh_keys)))
        items.sort()
        payload = repr((
            self.archetype, self.primary_set, self.secondary_set,
            self.epic_set, items
        ))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()


# ── HTML helpers ────────────────────────────────────────────────────────────

_BR_RE = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(
    r"</(?:li|p|div|tr|h[1-6]|blockquote|ul|ol)\s*>", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """Convert post body_html to plain text preserving line breaks.
    Treats <br>, </li>, </p>, etc. as newline boundaries — important for
    forum posts that wrap each enhancement slot in a list item."""
    text = _BR_RE.sub("\n", html)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    return unescape(text)


# ── Build-block extraction ──────────────────────────────────────────────────

# Each block is a header line like:
#   |MBD;25373;1635;2180;BASE64;|
#   |MxDz;1741;765;1530;HEX;|
# followed by an arbitrary number of |...| payload lines.
_BLOCK_HEADER_RE = re.compile(
    r"\|(MBD|MxDz|MxDu);\d+;\d+;\d+(?:;[A-Za-z0-9]*)?;\|"
)


def find_build_blocks(text: str) -> list[tuple[str, str]]:
    """
    Locate Mids build blocks in plain text. Returns a list of (kind, raw_block)
    tuples where kind is 'MBD' | 'MxDz' | 'MxDu' and raw_block contains the
    header line + payload lines (joined with newlines, leading/trailing
    whitespace stripped).

    A block ends at the first line that does not start with '|'.
    """
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = _BLOCK_HEADER_RE.search(line)
        if not m:
            i += 1
            continue

        kind = m.group(1)
        # Header may be embedded in surrounding text. Strip prose before
        # and after the |...;| header.
        header = line[m.start():m.end()]
        block_lines = [header]
        j = i + 1
        while j < len(lines):
            l = lines[j].strip()
            if not l:
                j += 1
                continue
            if not l.startswith("|"):
                break
            # Trim trailing prose like '[/code]' after the last '|'.
            last_pipe = l.rfind("|")
            if last_pipe <= 0:
                break
            block_lines.append(l[:last_pipe + 1])
            j += 1
        blocks.append((kind, "\n".join(block_lines)))
        i = j

    return blocks
