"""Maps archetype display names to icon filenames under static/at/."""
from __future__ import annotations

_MAP: dict[str, tuple[str, str]] = {
    # display name -> (50px filename, 100px filename)
    "Arachnos Soldier": ("AT-AS-Icon50.png",         "AT-AS-Icon100.png"),
    "Arachnos Widow":   ("AT-AW-Icon50.png",         "AT-AW-Icon100.png"),
    "Blaster":          ("AT-Blaster-Icon50.png",    "AT-Blaster-Icon100.png"),
    "Brute":            ("AT-Brute-Icon50.png",      "AT-Brute-Icon100.png"),
    "Controller":       ("AT-Controller-Icon50.png", "AT-Controller-Icon100.png"),
    "Corruptor":        ("AT-Corruptor-Icon50.png",  "AT-Corruptor-Icon100.png"),
    "Defender":         ("AT-Defender-Icon50.png",   "AT-Defender-Icon100.png"),
    "Dominator":        ("AT-Dominator-Icon50.png",  "AT-Dominator-Icon100.png"),
    "Mastermind":       ("AT-Mastermind-Icon50.png", "AT-Mastermind-Icon100.png"),
    "Peacebringer":     ("AT-PB-Icon50.png",         "AT-PB-Icon100.png"),
    "Scrapper":         ("AT-Scrapper-Icon50.png",   "AT-Scrapper-Icon100.png"),
    "Sentinel":         ("AT-Sentinel-Icon50.png",   "AT-Sentinel-Icon100.png"),
    "Stalker":          ("AT-Stalker-Icon50.png",    "AT-Stalker-Icon100.png"),
    "Tanker":           ("AT-Tanker-Icon50.png",     "AT-Tanker-Icon100.png"),
    "Warshade":         ("AT-WS-Icon50.png",         "AT-WS-Icon100.png"),
}

def icon_for_at(name: str, size: int = 50) -> str | None:
    """Return icon filename for an archetype, or None. Size must be 50 or 100."""
    entry = _MAP.get(name)
    if not entry:
        return None
    return entry[0] if size == 50 else entry[1]
