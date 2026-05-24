"""
Maps enhancement display strings to icon filenames under static/enh/.
Usage: icon_for_enh("Luck of the Gambler: Defense/Endurance") -> "sLuckOfTheGambler.png"
Returns None if no icon is available.
"""
from __future__ import annotations
import re
from pathlib import Path

_ICONS_DIR = Path(__file__).parent / "static" / "enh"

# ── manual overrides (exact display set-name -> filename) ─────────────────────
# Covers abbreviated filenames, typos in asset names, AO_/EO_ sets, etc.
_MANUAL: dict[str, str] = {
    # Typos / abbreviations in asset filenames
    "Adjusted Targeting":               "sAdjustedTargetting.png",
    "Adrenal Adjustment":               "sAdrenalAdj.png",
    "Basilisk's Gaze":                  "Basilisk.png",
    "Blessing of the Zephyr":           "Zephyr.png",
    "Cacophany":                        "sCacophony.png",
    "Calibrated Accuracy":              "sCalibratedAcc.png",
    "Dark Watcher's Despair":           "sDarkWatcher.png",
    "Efficacy Adaptor":                 "sEfficiencyAdaptor.png",
    "Encouraged Accuracy":              "sEncouragedAcc.png",
    "Energy Manipulator":               "sEnergyManip.png",
    "Exploited Vulnerability":          "sExploitVuln.png",
    "Fortunata Hypnosis":               "sFortunateHyp.png",
    "Gaussian's Synchronized Fire-Control": "sGaussianSF.png",
    "Gravitational Anchor":             "sGravAnchor.png",
    "Performance Shifter":              "sPerformanceSHift.png",
    "Rooting Grasp":                    "sRoothingGrasp.png",
    "Soulbound Allegiance":             "sSoulboaundAll.png",
    "Sovereign Right":                  "sSoverignRight.png",
    "Time & Space Manipulation":        "sSpaceTimeManipulation.png",
    "Touch of Lady Grey":               "sTouchofLadyGray.png",
    "Touch of the Nictus":              "TouchOfNictus.png",
    "Undermined Defenses":              "sUndermined.png",
    "Overwhelming Force":               "AO_Overwhelming_Force.png",

    # EO_ Winter Origin sets
    "Avalanche":                        "EO_Avalanche.png",
    "Entomb":                           "EO_Entomb.png",
    "Winter's Bite":                    "EO_WintersBite.png",
    "Superior Avalanche":               "SEO_Avalanche.png",
    "Superior Entomb":                  "SEO_Entomb.png",
    "Superior Winter's Bite":           "SEO_WintersBite.png",
    "Superior Blistering Cold":         "SEO_BlisteringCold.png",
    "Superior Frozen Blast":            "suFrozen_Blast.png",

    # AO_ Archetype Origin sets (Blaster)
    "Blaster's Wrath":                  "AO_Blaster1.png",
    "Defiant Barrage":                  "AO_Blaster2.png",
    "Superior Blaster's Wrath":         "SAO_Blaster1.png",
    "Superior Defiant Barrage":         "SAO_Blaster2.png",
    # AO_ Brute
    "Brute's Fury":                     "AO_Brute1.png",
    "Unrelenting Fury":                 "AO_Brute2.png",
    "Superior Brute's Fury":            "SAO_Brute1.png",
    "Superior Unrelenting Fury":        "SAO_Brute2.png",
    # AO_ Controller
    "Overpowering Presence":            "AO_Controller2.png",
    "Will of the Controller":           "AO_Controller1.png",
    "Superior Overpowering Presence":   "SAO_Controller2.png",
    "Superior Will of the Controller":  "SAO_Controller1.png",
    # AO_ Corruptor
    "Malice of the Corruptor":          "AO_Corruptor1.png",
    "Scourging Blast":                  "AO_Corruptor2.png",
    "Superior Malice of the Corruptor": "SAO_Corruptor1.png",
    "Superior Scourging Blast":         "SAO_Corruptor2.png",
    # AO_ Defender
    "Defender's Bastion":               "AO_Defender1.png",
    "Vigilant Assault":                 "AO_Defender2.png",
    "Superior Defender's Bastion":      "SAO_Defender1.png",
    "Superior Vigilant Assault":        "SAO_Defender2.png",
    # AO_ Dominator
    "Ascendency of the Dominator":      "AO_Dominator1.png",
    "Dominating Grasp":                 "AO_Dominator2.png",
    "Superior Ascendency of the Dominator": "SAO_Dominator1.png",
    "Superior Dominating Grasp":        "SAO_Dominator2.png",
    # AO_ Kheldian
    "Kheldian's Grace":                 "AO_Kheldian1.png",
    "Essence Transfer":                 "AO_Kheldian2.png",
    "Superior Kheldian's Grace":        "SAO_Kheldian1.png",
    "Superior Essence Transfer":        "SAO_Kheldian2.png",
    # AO_ Mastermind
    "Command of the Mastermind":        "AO_Mastermind1.png",
    "Mark of Supremacy":                "AO_Mastermind2.png",
    "Superior Command of the Mastermind": "SAO_Mastermind1.png",
    "Superior Mark of Supremacy":       "SAO_Mastermind2.png",
    # AO_ Scrapper
    "Scrapper's Strike":                "AO_Scrapper1.png",
    "Critical Strikes":                 "AO_Scrapper2.png",
    "Superior Scrapper's Strike":       "SAO_Scrapper1.png",
    "Superior Critical Strikes":        "SAO_Scrapper2.png",
    # AO_ Stalker
    "Stalker's Guile":                  "AO_Stalker1.png",
    "Assassin's Mark":                  "AO_Stalker2.png",
    "Superior Stalker's Guile":         "SAO_Stalker1.png",
    "Superior Assassin's Mark":         "SAO_Stalker2.png",
    # AO_ Tanker
    "Gauntleted Fist":                  "AO_Tanker1.png",
    "Might of the Tanker":              "AO_Tanker2.png",
    "Superior Gauntleted Fist":         "SAO_Tanker1.png",
    "Superior Might of the Tanker":     "SAO_Tanker2.png",
    # AO_ Arachnos
    "Dominion of Arachnos":             "AO_Arachnos1.png",
    "Spider's Bite":                    "AO_Arachnos2.png",
    "Superior Dominion of Arachnos":    "SAO_Arachnos1.png",
    "Superior Spider's Bite":           "SAO_Arachnos2.png",
    # AO_ Sentinel (Homecoming-only AT)
    "Opportunity Strikes":              "AO_Sentinel1.png",
    "Sentinel's Ward":                  "AO_Sentinel2.png",
    "Superior Opportunity Strikes":     "SAO_Sentinel1.png",
    "Superior Sentinel's Ward":         "SAO_Sentinel2.png",

    # Homecoming-specific sets (from HC database images)
    "Artillery":                        "Artillery.png",
    "Bombardment":                      "Bombardment.png",
    "Cupid's Crush":                    "cupids_crush.png",
    "Experienced Marksman":             "eMarksman.png",
    "Hypersonic":                       "Hypersonic.png",
    "Ice Mistral's Torment":            "Ice_Mistrals_Torment.png",
    "Launch":                           "Launch.png",
    "Power Transfer":                   "Power_Transfer.png",
    "Preemptive Optimization":          "Preemptive_Optimization.png",
    "Sudden Acceleration":              "sSuddenAcceleration.png",
    "Synapse's Shock":                  "Synapse_Shock.png",
    "Thrust":                           "Thrust.png",
    "Warp":                             "Warp.png",

    # Generic Invention IOs -> basic effect icons
    "Invention: Disorient Duration":     "Stun.png",
    # D-Sync enhancements (all share one icon)
    **{f"Invention: D-Sync {s}": "dsync.png" for s in (
        "Acceleration", "Binding", "Conduit", "Containment", "Deceleration",
        "Drain", "Efficiency", "Elusivity", "Empowerment", "Extension",
        "Fortification", "Guidance", "Marginalization", "Obfuscation",
        "Optimization", "Provocation", "Reconstitution", "Reconstruction",
        "Shifting", "Siphon",
    )},
    # Obscure HO sub-types
    "Invention: Ectosome Exposure":     "HOCytoskeleton.png",
    "Invention: Vesicle Exposure":      "HOGolgi.png",
    "Invention: Stereocilia Exposure":  "HOCytoskeleton.png",
    "Invention: Amyloplast Exposure":   "HOCytoskeleton.png",
    "Invention: Karyoplasm Exposure":   "HONucleolus.png",
    "Invention: Microtubule Exposure":  "HOMicrofilament.png",
    "Invention: Microvillus Exposure":  "HOMembrane.png",
    "Invention: Chromatin Exposure":    "HONucleolus.png",
    "Invention: Chloroplast Exposure":  "HOGolgi.png",
    # Generic Invention IOs -> basic effect icons
    "Invention: Accuracy":              "Acc.png",
    "Invention: Damage Increase":       "Damage.png",
    "Invention: Defense Buff":          "Defbuff.png",
    "Invention: Defense Debuff":        "DefDebuff.png",
    "Invention: Endurance Modification": "EndMod.png",
    "Invention: Endurance Reduction":   "EndRdx.png",
    "Invention: Fear Duration":         "Fear.png",
    "Invention: Flight Speed":          "Fly.png",
    "Invention: Healing":               "Heal.png",
    "Invention: Hold Duration":         "Hold.png",
    "Invention: Immobilisation Duration": "Immob.png",
    "Invention: Interrupt Reduction":   "Interrupt.png",
    "Invention: Jumping":               "Jump.png",
    "Invention: Knockback Distance":    "Knock.png",
    "Invention: Range":                 "Range.png",
    "Invention: Recharge Reduction":    "Recharge.png",
    "Invention: Resist Damage":         "DamRes.png",
    "Invention: Run Speed":             "Run.png",
    "Invention: Sleep Duration":        "Sleep.png",
    "Invention: Slow":                  "Slow.png",
    "Invention: Threat Duration":       "Threat.png",
    "Invention: To Hit Buff":           "ToHitBuff.png",
    "Invention: To Hit Debuff":         "ToHitDebuff.png",
    "Invention: Confuse Duration":      "Confuse.png",
    # HO (Hamidon Origins)
    "Invention: Centriole Exposure":    "HOCentriole.png",
    "Invention: Cytoskeleton Exposure": "HOCytoskeleton.png",
    "Invention: Endoplasm Exposure":    "HOEndoplasm.png",
    "Invention: Enzyme Exposure":       "HOEnzyme.png",
    "Invention: Golgi Exposure":        "HOGolgi.png",
    "Invention: Lysosome Exposure":     "HOLysosome.png",
    "Invention: Membrane Exposure":     "HOMembrane.png",
    "Invention: Microfilament Exposure": "HOMicrofilament.png",
    "Invention: Nucleolus Exposure":    "HONucleolus.png",
    "Invention: Peroxisome Exposure":   "HOPeroxisome.png",
    "Invention: Ribosome Exposure":     "HORibosome.png",
    # Hydra Origins
    "Invention: Electron Particles":    "HYElectron.png",
    "Invention: Positron Particles":    "HYPositron.png",
    "Invention: Quark Partciles":       "HYQuark.png",
    "Invention: Theta Particles":       "HYTheta.png",
    # Thread salvage
    "Invention: Citrine Shard":         "TNCitrine.png",
    "Invention: Diamond Shard":         "TNDiamond.png",
    "Invention: Peridont Shard":        "TNPeridont.png",
    "Invention: Selenite Shard":        "TNSelenite.png",
    "Invention: Tanzenite Shard":       "TNTanzenite.png",
}

# ── auto-match: strip s/su prefix, normalise, match ──────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def _build_auto() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in _ICONS_DIR.glob("*.png"):
        stem = path.stem
        fname = path.name
        for prefix in ("su", "s"):
            if stem.startswith(prefix) and len(stem) > len(prefix):
                key = _norm(stem[len(prefix):])
                mapping.setdefault(key, fname)
                break
        else:
            mapping.setdefault(_norm(stem), fname)
    return mapping

_AUTO = _build_auto()

# Pre-normalise manual keys for fast lookup
_MANUAL_NORM: dict[str, str] = {_norm(k): v for k, v in _MANUAL.items()}

# Cache to avoid repeated normalisation
_cache: dict[str, str | None] = {}


def icon_for_enh(display: str) -> str | None:
    """Return icon filename for an enhancement display string, or None."""
    if display in _cache:
        return _cache[display]

    # Manual lookup first (exact key, then normalised key)
    result = _MANUAL.get(display) or _MANUAL_NORM.get(_norm(display))
    if result is None:
        # Extract set name (before ':') and try auto-match
        set_name = display.split(":")[0].strip() if ":" in display else display
        result = _MANUAL.get(set_name)
        if result is None:
            key = _norm(set_name)
            result = _MANUAL_NORM.get(key) or _AUTO.get(key)

    # Verify file exists (silently drop bad references)
    if result and not (_ICONS_DIR / result).exists():
        result = None

    _cache[display] = result
    return result
