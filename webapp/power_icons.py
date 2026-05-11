"""
Maps (powerset_display, power_display) -> static path for per-power icons.
Currently covers pool powers and patron pools; primary/secondary sets TBD.
"""
from __future__ import annotations

# Each entry: (powerset_display, power_display) -> static filename
# Filename is relative to webapp/static/
_MAP: dict[tuple[str, str], str] = {
    # ── Pool Powers ───────────────────────────────────────────────────────────

    # Concealment
    ("Concealment", "Grant Invisibility"):  "pwr-pool/Concealment/Concealment-GrantInvis-50.png",
    ("Concealment", "Infiltration"):        "pwr-pool/Concealment/Concealment-Infiltration-50.png",
    ("Concealment", "Misdirection"):        "pwr-pool/Concealment/Concealment-Misdirection-50.png",
    ("Concealment", "Phase Shift"):         "pwr-pool/Concealment/Concealment-PhaseShift-50.png",
    ("Concealment", "Stealth"):             "pwr-pool/Concealment/Concealment-Stealth-50.png",

    # Experimentation
    ("Experimentation", "Adrenal Booster"):         "pwr-pool/Experimentation/Experimentation-AdBoost-50.png",
    ("Experimentation", "Corrosive Vial"):           "pwr-pool/Experimentation/Experimentation-CorVial-50.png",
    ("Experimentation", "Experimental Injection"):   "pwr-pool/Experimentation/Experimentation-ExpInj-50.png",
    ("Experimentation", "Speed of Sound"):           "pwr-pool/Experimentation/Experimentation-SpeedSound-50.png",
    ("Experimentation", "Toxic Dart"):               "pwr-pool/Experimentation/Experimentation-ToxDart-50.png",

    # Fighting
    ("Fighting", "Boxing"):       "pwr-pool/Fighting/Fighting-Boxing-50.png",
    ("Fighting", "Cross Punch"):  "pwr-pool/Fighting/Fighting-CrossPunch-50.png",
    ("Fighting", "Kick"):         "pwr-pool/Fighting/Fighting-Kick-50.png",
    ("Fighting", "Tough"):        "pwr-pool/Fighting/Fighting-Tough-50.png",
    ("Fighting", "Weave"):        "pwr-pool/Fighting/Fighting-Weave-50.png",

    # Flight
    ("Flight", "Air Superiority"):    "pwr-pool/Flight/Flight-AS-Icon50.png",
    ("Flight", "Evasive Maneuvers"):  "pwr-pool/Flight/Flight-Evasive-Maneuvers-Icon50.png",
    ("Flight", "Fly"):                "pwr-pool/Flight/Flight-Fly-Icon50.png",
    ("Flight", "Group Fly"):          "pwr-pool/Flight/Flight-GF-Icon50.png",
    ("Flight", "Hover"):              "pwr-pool/Flight/Flight-Hover-Icon50.png",
    ("Flight", "Afterburner"):        "pwr-pool/Flight/Flight-Afterburner-Icon50.png",

    # Force of Will
    ("Force of Will", "Mighty Leap"):         "pwr-pool/Force of Will/FoW-MightyLeap-50.png",
    ("Force of Will", "Project Will"):        "pwr-pool/Force of Will/FoW-ProjectWill-50.png",
    ("Force of Will", "Takeoff"):             "pwr-pool/Force of Will/FoW-Takeoff-50.png",
    ("Force of Will", "Unleash Potential"):   "pwr-pool/Force of Will/FoW-UnleashPot-50.png",
    ("Force of Will", "Wall of Force"):       "pwr-pool/Force of Will/FoW-WallForce-50.png",
    ("Force of Will", "Weaken Resolve"):      "pwr-pool/Force of Will/FoW-WeakResolve-50.png",

    # Leadership
    ("Leadership", "Assault"):       "pwr-pool/Leadership/Leadership-Assault-50.png",
    ("Leadership", "Maneuvers"):     "pwr-pool/Leadership/Leadership-Maneuvers-50.png",
    ("Leadership", "Tactics"):       "pwr-pool/Leadership/Leadership-Tactics-50.png",
    ("Leadership", "Vengeance"):     "pwr-pool/Leadership/Leadership-Vengeance-50.png",
    ("Leadership", "Victory Rush"):  "pwr-pool/Leadership/Leadership-VicRush-50.png",

    # Leaping
    ("Leaping", "Acrobatics"):      "pwr-pool/Leaping/Leaping-Acrobatics-50.png",
    ("Leaping", "Combat Jumping"):  "pwr-pool/Leaping/Leaping-CombJump-50.png",
    ("Leaping", "Double Jump"):     "pwr-pool/Leaping/Leaping-DoubleJump-50.png",
    ("Leaping", "Jump Kick"):       "pwr-pool/Leaping/Leaping-JumpKick-50.png",
    ("Leaping", "Spring Attack"):   "pwr-pool/Leaping/Leaping-SpringAttack-50.png",
    ("Leaping", "Super Jump"):      "pwr-pool/Leaping/Leaping-SuperJump-50.png",

    # Medicine
    ("Medicine", "Aid Other"):      "pwr-pool/Medicine/Medicine-AidOther-50.png",
    ("Medicine", "Aid Self"):       "pwr-pool/Medicine/Medicine-AidSelf-50.png",
    ("Medicine", "Field Medic"):    "pwr-pool/Medicine/Medicine-FieldMedic-50.png",
    ("Medicine", "Injection"):      "pwr-pool/Medicine/Medicine-Injection-50.png",
    ("Medicine", "Resuscitate"):    "pwr-pool/Medicine/Medicine-Resuscitate-50.png",

    # Presence
    ("Presence", "Intimidate"):    "pwr-pool/Presence/Presence-Intimidate-50.png",
    ("Presence", "Invoke Panic"):  "pwr-pool/Presence/Presence-InvokePanic-50.png",
    ("Presence", "Pacify"):        "pwr-pool/Presence/Presence-Pacify-50.png",
    ("Presence", "Provoke"):       "pwr-pool/Presence/Presence-Provoke-50.png",
    ("Presence", "Unrelenting"):   "pwr-pool/Presence/Presence-Unrelenting-50.png",

    # Sorcery
    ("Sorcery", "Arcane Bolt"):         "pwr-pool/Sorcery/Sorcery-ArcaneBolt-50.png",
    ("Sorcery", "Enflame"):             "pwr-pool/Sorcery/Sorcery-Enflame-50.png",
    ("Sorcery", "Mystic Flight"):       "pwr-pool/Sorcery/Sorcery-MysticFlight-50.png",
    ("Sorcery", "Rune of Protection"):  "pwr-pool/Sorcery/Sorcery-RuneProtection-50.png",
    ("Sorcery", "Spirit Ward"):         "pwr-pool/Sorcery/Sorcery-SpiritWard-50.png",

    # Speed
    ("Speed", "Burnout"):     "pwr-pool/Speed/Speed-Burnout-50.png",
    ("Speed", "Flurry"):      "pwr-pool/Speed/Speed-Flurry-50.png",
    ("Speed", "Hasten"):      "pwr-pool/Speed/Speed-Hasten-50.png",
    ("Speed", "Super Speed"): "pwr-pool/Speed/Speed-SuperSpeed-50.png",
    ("Speed", "Whirlwind"):   "pwr-pool/Speed/Speed-Whirlwind-50.png",

    # Teleportation
    ("Teleportation", "Combat Teleport"):   "pwr-pool/Teleport/Teleport-CombatTP-50.png",
    ("Teleportation", "Fold Space"):        "pwr-pool/Teleport/Teleport-FoldSpace-50.png",
    ("Teleportation", "Team Teleport"):     "pwr-pool/Teleport/Teleport-TeamTP-50.png",
    ("Teleportation", "Teleport"):          "pwr-pool/Teleport/Teleport-Teleport-50.png",
    ("Teleportation", "Teleport Target"):   "pwr-pool/Teleport/Teleport-TPTarget-50.png",

    # ── Patron Power Pools ────────────────────────────────────────────────────

    # Leviathan Mastery
    ("Leviathan Mastery", "Arctic Breath"):     "pwr-patron/Leviathan Mastery/Leviathan-ArcticBreath-50.png",
    ("Leviathan Mastery", "Bile Spray"):        "pwr-patron/Leviathan Mastery/Leviathan-BileSpray-50.png",
    ("Leviathan Mastery", "Hibernate"):         "pwr-patron/Leviathan Mastery/Leviathan-Hibernate-50.png",
    ("Leviathan Mastery", "Knockout Blow"):     "pwr-patron/Leviathan Mastery/Leviathan-KnockoutBlow-50.png",
    ("Leviathan Mastery", "School of Sharks"):  "pwr-patron/Leviathan Mastery/Leviathan-SchoolSharks-50.png",
    ("Leviathan Mastery", "Shark Skin"):        "pwr-patron/Leviathan Mastery/Leviathan-SharkSkin-50.png",
    ("Leviathan Mastery", "Spirit Shark"):      "pwr-patron/Leviathan Mastery/Leviathan-SpiritShark-50.png",
    ("Leviathan Mastery", "Spirit Shark Jaws"): "pwr-patron/Leviathan Mastery/Leviathan-SpiritSharkJaws-50.png",
    ("Leviathan Mastery", "Summon Coralax"):    "pwr-patron/Leviathan Mastery/Leviathan-SummonCoralax-50.png",
    ("Leviathan Mastery", "Summon Guardian"):   "pwr-patron/Leviathan Mastery/Leviathan-SpiritShark2-50.png",
    ("Leviathan Mastery", "Water Spout"):       "pwr-patron/Leviathan Mastery/Leviathan-WaterSpout-50.png",

    # Mace Mastery
    ("Mace Mastery", "Coordinated Targeting"):  "pwr-patron/Mace Mastery/Mace-CoordinatingTargeting-50.png",
    ("Mace Mastery", "Disruptor Blast"):        "pwr-patron/Mace Mastery/Mace-DisruptorBlast-50.png",
    ("Mace Mastery", "Focused Accuracy"):       "pwr-patron/Mace Mastery/Mace-FocusedAccuracy-50.png",
    ("Mace Mastery", "Mace Beam"):              "pwr-patron/Mace Mastery/Mace-MaceBeam-50.png",
    ("Mace Mastery", "Mace Beam Volley"):       "pwr-patron/Mace Mastery/Mace-MaceBeamVol-50.png",
    ("Mace Mastery", "Mace Blast"):             "pwr-patron/Mace Mastery/Mace-MaceBlast-50.png",
    ("Mace Mastery", "Personal Force Field"):   "pwr-patron/Mace Mastery/Mace-PerForceField-50.png",
    ("Mace Mastery", "Poisonous Ray"):          "pwr-patron/Mace Mastery/Mace-PoisonousRay-50.png",
    ("Mace Mastery", "Power Boost"):            "pwr-patron/Mace Mastery/Mace-PowerBoost-50.png",
    ("Mace Mastery", "Pulverize"):              "pwr-patron/Mace Mastery/Mace-Pulverize-50.png",
    ("Mace Mastery", "Scorpion Shield"):        "pwr-patron/Mace Mastery/Mace-ScorpionShield-50.png",
    ("Mace Mastery", "Shatter Armor"):          "pwr-patron/Mace Mastery/Mace-ShatterArmor-50.png",
    ("Mace Mastery", "Summon Arachnoids"):      "pwr-patron/Mace Mastery/Mace-Summon-50.png",
    ("Mace Mastery", "Web Cocoon"):             "pwr-patron/Mace Mastery/Mace-WebCocoon-50.png",
    ("Mace Mastery", "Web Envelope"):           "pwr-patron/Mace Mastery/Mace-WebEnvelope-50.png",

    # Mu Mastery
    ("Mu Mastery", "Ball Lightning"):       "pwr-patron/Mu Mastery/Mu-BallLightning-50.png",
    ("Mu Mastery", "Charged Armor"):        "pwr-patron/Mu Mastery/Mu-ChargedArmor-50.png",
    ("Mu Mastery", "Electric Shackles"):    "pwr-patron/Mu Mastery/Mu-ElectricShackles-50.png",
    ("Mu Mastery", "Electrifying Fences"):  "pwr-patron/Mu Mastery/Mu-ElectrifyingFences-50.png",
    ("Mu Mastery", "Energize"):             "pwr-patron/Mu Mastery/Mu-Energize-50.png",
    ("Mu Mastery", "Mu Bolts"):             "pwr-patron/Mu Mastery/Mu-MuBolts-50.png",
    ("Mu Mastery", "Mu Lightning"):         "pwr-patron/Mu Mastery/Mu-MuLightning-50.png",
    ("Mu Mastery", "Power Sink"):           "pwr-patron/Mu Mastery/Mu-PowerSink-50.png",
    ("Mu Mastery", "Power Boost"):          "pwr-patron/Mu Mastery/Mu-SurgePower-50.png",
    ("Mu Mastery", "Static Discharge"):     "pwr-patron/Mu Mastery/Mu-StaticDischarge-50.png",
    ("Mu Mastery", "Summon Mu Guardian"):   "pwr-patron/Mu Mastery/Mu-Summon-50.png",
    ("Mu Mastery", "Thunder Strike"):       "pwr-patron/Mu Mastery/Mu-ThunderStrike-50.png",
    ("Mu Mastery", "Zapp"):                 "pwr-patron/Mu Mastery/Mu-Zapp-50.png",

    # Soul Mastery
    ("Soul Mastery", "Dark Blast"):         "pwr-patron/Soul Mastery/Soul-DarkBlast-50.png",
    ("Soul Mastery", "Dark Consumption"):   "pwr-patron/Soul Mastery/Soul-DarkConsumption-50.png",
    ("Soul Mastery", "Dark Embrace"):       "pwr-patron/Soul Mastery/Soul-DarkEmbrace-50.png",
    ("Soul Mastery", "Darkest Night"):      "pwr-patron/Soul Mastery/Soul-DarkestNight-50.png",
    ("Soul Mastery", "Dark Obliteration"):  "pwr-patron/Soul Mastery/Soul-DarkObliteration-50.png",
    ("Soul Mastery", "Gloom"):              "pwr-patron/Soul Mastery/Soul-Gloom-50.png",
    ("Soul Mastery", "Midnight Grasp"):     "pwr-patron/Soul Mastery/Soul-MidnightGrasp-50.png",
    ("Soul Mastery", "Moonbeam"):           "pwr-patron/Soul Mastery/Soul-Moonbeam-50.png",
    ("Soul Mastery", "Night Fall"):         "pwr-patron/Soul Mastery/Soul-NightFall-50.png",
    ("Soul Mastery", "Oppressive Gloom"):   "pwr-patron/Soul Mastery/Soul-OppressiveGloom-50.png",
    ("Soul Mastery", "Power Boost"):        "pwr-patron/Soul Mastery/Soul-PowerBoost-50.png",
    ("Soul Mastery", "Shadow Meld"):        "pwr-patron/Soul Mastery/Soul-ShadowMeld-50.png",
    ("Soul Mastery", "Soul Drain"):         "pwr-patron/Soul Mastery/Soul-SoulDrain-50.png",
    ("Soul Mastery", "Soul Storm"):         "pwr-patron/Soul Mastery/Soul-SoulStorm-50.png",
    ("Soul Mastery", "Soul Tentacles"):     "pwr-patron/Soul Mastery/Soul-SoulTentacles-50.png",
    ("Soul Mastery", "Summon Mistress"):    "pwr-patron/Soul Mastery/Soul-Summon-50.png",
}

_STATIC_ROOT = __import__("pathlib").Path(__file__).parent / "static"


def icon_for_power(ps_display: str, power_display: str) -> str | None:
    """Return static filename for a power icon, or None."""
    path = _MAP.get((ps_display, power_display))
    if path and (_STATIC_ROOT / path).exists():
        return path
    return None
