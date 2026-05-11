"""
Banned powers — auto-toggles, click-cycle effects, and form-shifts that
should not take real slots. Inherited from coh-enhscan.py's banned_powers
list with a few additions for newer powers.

These are filtered at extract time. If they appear slotted in a build it's
almost always either a parser misfire or a build-tool quirk; counting them
warps the stats for any pool that contains them.

Match is by display name (case-insensitive) — these names are unique
enough across the powerset hierarchy that a substring match is safe.
"""
from __future__ import annotations

BANNED_DISPLAY_NAMES: frozenset[str] = frozenset(name.lower() for name in [
    # Inherent toggles / form-shifts
    "Gauntlet",                 # Tanker inherent
    "Adaptation",               # Bio Armor toggle root
    "Offensive Adaptation",
    "Defensive Adaptation",
    "Efficient Adaptation",
    "Form of the Mind",         # Peacebringer/Warshade form-shifts
    "Form of the Soul",
    "Form of the Body",
    # Ammunition swaps (Dual Pistols)
    "Cryo Ammunition",
    "Incendiary Ammunition",
    "Chemical Ammunition",
    "Swap Ammo",
    # Stance-style toggles seen in newer sets
    "Defiance",                 # Blaster inherent (passive)
    "Quick Form",               # Khelds — instant form-toggle
    # Unslottable temp powers (visible only while parent power is active)
    "Jaunt",                    # Experimentation — appears while Speed of Sound is active
    "Translocation",            # Sorcery — appears while Mystic Flight is active
])


def is_banned(power_display_name: str) -> bool:
    return (power_display_name or "").lower() in BANNED_DISPLAY_NAMES
