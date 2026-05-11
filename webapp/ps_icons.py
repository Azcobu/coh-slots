"""
Maps powerset display names to static-relative icon paths.
Usage: icon_for_ps("Fire Blast") -> "ps/FireBlast.png"
       icon_for_ps("Flight")     -> "pwr-pool/Flight/Flight-Fly-Icon50.png"
Returns None if no icon is available.
"""
from __future__ import annotations
import re
from pathlib import Path

_ICONS_DIR = Path(__file__).parent / "static" / "ps"
_STATIC_ROOT = Path(__file__).parent / "static"

# Pool and patron powersets: use their own 50px per-power icons
# (the generic ps/ icons are only 16px and look blurry beside them).
_POOL_OVERRIDES: dict[str, str] = {
    "Concealment":      "pwr-pool/Concealment/Concealment-Stealth-50.png",
    "Experimentation":  "pwr-pool/Experimentation/Experimentation-AdBoost-50.png",
    "Fighting":         "pwr-pool/Fighting/Fighting-Boxing-50.png",
    "Flight":           "pwr-pool/Flight/Flight-Fly-Icon50.png",
    "Force of Will":    "pwr-pool/Force of Will/FoW-MightyLeap-50.png",
    "Leadership":       "pwr-pool/Leadership/Leadership-Maneuvers-50.png",
    "Leaping":          "pwr-pool/Leaping/Leaping-SuperJump-50.png",
    "Medicine":         "pwr-pool/Medicine/Medicine-AidSelf-50.png",
    "Presence":         "pwr-pool/Presence/Presence-Intimidate-50.png",
    "Sorcery":          "pwr-pool/Sorcery/Sorcery-MysticFlight-50.png",
    "Speed":            "pwr-pool/Speed/Speed-Hasten-50.png",
    "Teleportation":    "pwr-pool/Teleport/Teleport-Teleport-50.png",
    "Leviathan Mastery": "pwr-patron/Leviathan Mastery/Leviathan-WaterSpout-50.png",
    "Mace Mastery":      "pwr-patron/Mace Mastery/Mace-ScorpionShield-50.png",
    "Mu Mastery":        "pwr-patron/Mu Mastery/Mu-Zapp-50.png",
    "Soul Mastery":      "pwr-patron/Soul Mastery/Soul-SoulDrain-50.png",
}

# Manual overrides: display name -> filename
_MANUAL: dict[str, str] = {
    # Naming differences
    "Atomic Manipulation":      "RadiationArmor.png",
    "Speed":                    "SuperSpeed.png",
    "Claws":                    "ClawsHero.png",
    "Dark Assault":             "DarknessAssault.png",
    "Darkness Manipulation":    "DarkBlast.png",
    "Earth Assault":            "EarthControl.png",
    "Earth Mastery":            "StoneMastery.png",
    "Electrical Affinity":      "ElectricalMastery.png",
    "Electrical Blast":         "ElecBlast.png",
    "Electrical Melee":         "ElectricMelee.png",
    "Electricity Assault":      "i12_Sec_ElecAssault.png",
    "Fiery Assault":            "FireAssault.png",
    "Fiery Aura":               "FlireShield.png",
    "Icy Assault":              "IceAssault.png",
    "Martial Arts":             "MartialArtsHero.png",
    "Mental Manipulation":      "MindControl.png",
    "Pain Domination":          "PainDom.png",
    "Plant Manipulation":       "PlantControl.png",
    "Radioactive Assault":      "RadiationBlast.png",
    "Savage Assault":           "SavageMelee.png",
    "Shield Defense":           "ShieldDef.png",
    "Soul Mastery":             "DarkMastery.png",
    "Spines":                   "SpinesHero.png",
    "Storm Summoning":          "StormSummon.png",
    "Tactical Arrow":           "TrickArrow.png",
    "Teamwork":                 "Leadership.png",
    "Temporal Manipulation":    "TimeManipulation.png",
    "Training and Gadgets":     "Devices.png",

    # Patron pools (best-effort generic icons)
    "Arsenal Mastery":          "PatronRanged.png",
    "Leviathan Mastery":        "PatronDrain.png",
    "Mace Mastery":             "PatronShield.png",
    "Mu Mastery":               "PatronDMGBuff.png",

    # Arachnos-specific (i12_ prefixed icons)
    "Arachnos Soldier":         "i12_Pri_Soldier.png",
    "Bane Spider Soldier":      "i12_Pri_Bane.png",
    "Bane Spider Training":     "i12_Sec_Bane.png",
    "Crab Spider Soldier":      "i12_Pri_Crab.png",
    "Crab Spider Training":     "i12_Sec_Crab.png",
    "Fortunata Teamwork":       "i12_Sec_Fortunata.png",
    "Fortunata Training":       "i12_Pri_Fortunata.png",
    "Night Widow Training":     "i12_Pri_Nightwidow.png",
    "Widow Teamwork":           "i12_Sec_Widow.png",
    "Widow Training":           "i12_Pri_Widow.png",
    "Ninja Training":           "blaster_ninja_training.png",
}

# Auto-match: normalised filename stem -> filename
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def _build_auto() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in _ICONS_DIR.glob("*.png"):
        mapping.setdefault(_norm(path.stem), path.name)
    return mapping

_AUTO = _build_auto()
_MANUAL_NORM: dict[str, str] = {_norm(k): v for k, v in _MANUAL.items()}
_cache: dict[str, str | None] = {}


def icon_for_ps(display: str) -> str | None:
    """Return static-relative icon path for a powerset display name, or None."""
    if display in _cache:
        return _cache[display]

    # Pool/patron overrides use higher-res per-power icons.
    if display in _POOL_OVERRIDES:
        path = _POOL_OVERRIDES[display]
        result: str | None = path if (_STATIC_ROOT / path).exists() else None
        _cache[display] = result
        return result

    fname = _MANUAL.get(display) or _MANUAL_NORM.get(_norm(display)) or _AUTO.get(_norm(display))
    if fname and (_ICONS_DIR / fname).exists():
        result = f"ps/{fname}"
    else:
        result = None

    _cache[display] = result
    return result
