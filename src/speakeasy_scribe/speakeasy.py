"""What SpeakEasy 1.0.x accepts, taken from its Core/SpeakEasy_Db.lua and Core/SpeakEasy_Play.lua."""

DB_VERSION = 1
MAX_LINE_BYTES = 255
MAX_NAME_BYTES = 32
MAX_EMOTE_BYTES = 32
MAX_MACRO_NAME_BYTES = 16
MAX_SPELL_BYTES = 64
DEFAULT_ICON = 134400
WHEEL_SLOTS = 8
MAX_WHEEL_PAGES = 9
MAX_TRIGGER_SPELLS = 50
EMOTE_SLOT_PREFIX = "emote:"

CHANNELS = ("SAY", "EMOTE", "YELL", "PARTY", "RAID", "INSTANCE_CHAT", "AUTO")

EVENTS = {
    "ENTER_COMBAT": "You enter combat.",
    "LEAVE_COMBAT": "You leave combat.",
    "LOW_HEALTH": "Your health drops below `threshold` percent (not on Retail 12; works on Forever and Classic).",
    "DEATH": "You die.",
    "SPELL_CAST": "You cast one of the listed `spells` (an `item` fills {itemName}).",
    "EAT_DRINK": "You start eating or drinking ({itemName} is the food or drink).",
    "MOUNT": "You mount up.",
    "REST_AREA": "You enter an inn or a city.",
    "TARGET_NPC": "You target a living NPC.",
}

# Variables in the order of SpeakEasy's Insert variable menu.
VARIABLES = {
    "targetName": "Target's name, or the targetFallback setting (default 'friend') with no target.",
    "targetClass": "Target's class; blank with no target.",
    "targetRace": "Target's race; blank with no target.",
    "playerName": "Your character's name.",
    "playerClass": "Your class.",
    "playerRace": "Your race.",
    "zone": "Current zone.",
    "subZone": "Current sub-zone, or the zone when there is none.",
    "guild": "Your guild's name; blank without a guild.",
    "timeOfDay": "morning, afternoon, evening or night from the game clock.",
    "healthPercent": "Your health, such as 42%; blank on Retail 12.",
    "spellName": "The spell that set off a SPELL_CAST or EAT_DRINK trigger; blank otherwise.",
    "itemName": "The item that set off a SPELL_CAST or EAT_DRINK trigger; blank otherwise.",
}
TRIGGER_ONLY_VARIABLES = {"spellName", "itemName"}

RESERVED_IDS = {"mute", "speak", "debug"}

SETTINGS_DEFAULT = {
    "triggersMuted": False,
    "speakOnAnyKey": True,
    "wheelScale": 1,
    "wheelRememberPage": True,
    "primeTimeout": 8,
    "globalTriggerGap": 10,
    "targetFallback": "friend",
    "minimapAngle": 225,
    "window": {},
    "prompt": {},
}
SETTINGS_RANGES = {
    "primeTimeout": (3, 60),
    "globalTriggerGap": (0, 300),
    "wheelScale": (0.5, 2),
}

COOLDOWN_RANGE = (0, 3600)
CHANCE_RANGE = (0, 100)
THRESHOLD_RANGE = (1, 99)
