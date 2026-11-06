-- Saved variables: defaults, the starter pack, clean-up of stored data, and
-- every change to scenes, lines and triggers.
local ADDON, L = ...

L.Db = {}

L.Db.VERSION = 1
L.Db.MAX_LINE = 255
L.Db.MAX_NAME = 32
L.Db.DEFAULT_ICON = 134400
L.Db.WHEEL_SLOTS = 8
L.Db.MAX_WHEEL_PAGES = 9
L.Db.MAX_TRIGGER_SPELLS = 50
-- A wheel slot holding an emote rather than a scene: "emote:DANCE".
L.Db.EMOTE_SLOT = "emote:"

L.Db.CHANNELS = { "SAY", "EMOTE", "YELL", "PARTY", "RAID", "INSTANCE_CHAT", "AUTO" }
L.Db.EVENTS = { "ENTER_COMBAT", "LEAVE_COMBAT", "LOW_HEALTH", "DEATH", "SPELL_CAST", "EAT_DRINK", "MOUNT", "REST_AREA", "TARGET_NPC" }

-- Words /speakeasy treats as commands, so no scene id may take them.
local RESERVED_IDS = { mute = true, speak = true, debug = true }

local SETTINGS_DEFAULT = {
    triggersMuted = false,
    speakOnAnyKey = true,
    wheelScale = 1,
    wheelRememberPage = true,
    primeTimeout = 8,
    globalTriggerGap = 10,
    targetFallback = "friend",
    minimapAngle = 225,
    window = {},
    prompt = {},
}

-- input: a list of values
-- output: a table with each value as a key set to true
-- Turns a list into a set for quick membership checks.
local function SetOf(list)
    local set = {}
    for _, value in ipairs(list) do
        set[value] = true
    end

    return set
end

local VALID_CHANNEL = SetOf(L.Db.CHANNELS)
local VALID_EVENT = SetOf(L.Db.EVENTS)

-- input: nothing
-- output: the starter scenes and triggers
-- Builds the set a first install starts with.
local function Starter()
    -- input: a line's text and an optional emote token
    -- output: an enabled line
    -- Builds one starter line.
    local function Line(text, emote)
        return { text = text, emote = emote, enabled = true }
    end

    return {
        scenes = {
            { id = "greeting", name = "Greeting", icon = L.Db.DEFAULT_ICON, channel = "SAY", cooldown = 2, enabled = true, lines = {
                Line("Well met, {targetName}.", "WAVE"),
                Line("Good {timeOfDay}, {targetName}."),
                Line("Light keep you, friend."),
                Line("", "BOW"),
            } },
            { id = "farewell", name = "Farewell", icon = L.Db.DEFAULT_ICON, channel = "SAY", defaultEmote = "WAVE", cooldown = 2, enabled = true, lines = {
                Line("Safe travels, {targetName}."),
                Line("Until next time."),
                Line("May the road be kind to you."),
            } },
            { id = "combat", name = "Combat", icon = 132147, channel = "SAY", cooldown = 2, enabled = true, lines = {
                Line("For {zone}!", "CHARGE"),
                Line("Is that all you've got, {targetName}?"),
                Line("Not today.", "ROAR"),
                Line("Stand and fight!"),
            } },
            { id = "tavern", name = "Tavern", icon = L.Db.DEFAULT_ICON, channel = "SAY", cooldown = 2, enabled = true, lines = {
                Line("Another round for the table!", "CHEER"),
                Line("Any news from beyond {zone}?"),
                Line("Nothing like {subZone} on a quiet {timeOfDay}."),
            } },
        },
        triggers = {
            { event = "ENTER_COMBAT", options = { threshold = 30 }, sceneId = "combat", chance = 30, cooldown = 60, enabled = false },
        },
    }
end

-- input: a value and a byte limit
-- output: the value cut to the limit when it is a string, otherwise nil
-- Reads a stored string safely.
local function Text(value, limit)
    return type(value) == "string" and L.Util.Cut(value, limit) or nil
end

-- input: a value, bounds and a default
-- output: the value as a number inside the bounds, or the default
-- Reads a stored number safely and clamps it.
local function Number(value, low, high, default)
    value = tonumber(value)
    if not value then
        return default
    end

    return math.min(high, math.max(low, value))
end

-- input: a name or id and a table of ids already taken
-- output: a free id of lower case letters and digits
-- Derives a stable /speakeasy key from a name, adding a number when it is taken.
local function UniqueId(base, taken)
    local id = tostring(base):lower():gsub("[^%w]", "")
    if id == "" then
        id = "scene"
    end

    local candidate, number = id, 1
    while taken[candidate] or RESERVED_IDS[candidate] do
        number = number + 1
        candidate = id .. number
    end

    taken[candidate] = true

    return candidate
end

-- input: a stored line
-- output: a clean copy, or nil when it has neither text nor an emote
-- Rebuilds one line from stored data.
local function CleanLine(line)
    if type(line) ~= "table" then
        return nil
    end

    local text = Text(line.text, L.Db.MAX_LINE) or ""
    local emote = Text(line.emote, 32)
    if emote == "" then
        emote = nil
    end

    if strtrim(text) == "" and not emote then
        return nil
    end

    return { text = text, emote = emote, enabled = line.enabled ~= false }
end

-- input: a stored scene and a table of ids already taken
-- output: a clean copy, or nil when it is not a table
-- Rebuilds one scene and its lines from stored data.
local function CleanScene(scene, taken)
    if type(scene) ~= "table" then
        return nil
    end

    local name = strtrim(Text(scene.name, L.Db.MAX_NAME) or "")
    if name == "" then
        name = Text(scene.id, L.Db.MAX_NAME) or L.Text.NEW_SCENE
    end

    local clean = {
        id = UniqueId(type(scene.id) == "string" and scene.id or name, taken),
        name = name,
        icon = tonumber(scene.icon) or L.Db.DEFAULT_ICON,
        channel = VALID_CHANNEL[scene.channel] and scene.channel or "SAY",
        defaultEmote = Text(scene.defaultEmote, 32),
        cooldown = Number(scene.cooldown, 0, 3600, 2),
        enabled = scene.enabled ~= false,
        macroName = Text(scene.macroName, 16),
        lines = {},
    }

    if clean.defaultEmote == "" then
        clean.defaultEmote = nil
    end

    for _, line in ipairs(type(scene.lines) == "table" and scene.lines or {}) do
        clean.lines[#clean.lines + 1] = CleanLine(line)
    end

    return clean
end

-- input: a stored trigger
-- output: a clean copy, or nil when its event is unknown
-- Rebuilds one trigger and its options from stored data.
local function CleanTrigger(trigger)
    if type(trigger) ~= "table" or not VALID_EVENT[trigger.event] then
        return nil
    end

    local options = type(trigger.options) == "table" and trigger.options or {}

    -- A trigger keeps only the options its own event uses, so ones left from
    -- another event (say an item, after switching to eat or drink) cannot linger.
    local isSpell = trigger.event == "SPELL_CAST"

    -- Spell triggers watch a list of spells, each perhaps from an item. Ones
    -- saved before the list held a single spell and item directly.
    local stored = type(options.spells) == "table" and options.spells or {}
    if type(options.spell) == "string" and #stored == 0 then
        stored = { { spell = options.spell, item = options.item } }
    end

    local spells = {}
    for _, entry in ipairs(isSpell and stored or {}) do
        local spell = type(entry) == "table" and Text(entry.spell, 64)
        if spell and strtrim(spell) ~= "" and #spells < L.Db.MAX_TRIGGER_SPELLS then
            spells[#spells + 1] = { spell = spell, item = Text(entry.item, 64) }
        end
    end

    return {
        event = trigger.event,
        sceneId = Text(trigger.sceneId, 64) or "",
        chance = Number(trigger.chance, 0, 100, 30),
        cooldown = Number(trigger.cooldown, 0, 3600, 60),
        enabled = trigger.enabled ~= false,
        options = {
            threshold = Number(options.threshold, 1, 99, 30),
            spells = isSpell and spells or nil,
        },
    }
end

-- input: a list of scenes
-- output: a wheel page holding the first 8 of them
-- Builds the first wheel page when none is stored.
local function DefaultPage(scenes)
    local page = {}
    for slot = 1, L.Db.WHEEL_SLOTS do
        page[slot] = scenes[slot] and scenes[slot].id or ""
    end

    return page
end

-- input: stored wheel pages and the set's scenes
-- output: between 1 and MAX_WHEEL_PAGES pages of 8 slots, each a scene id,
--         an emote slot or "" for empty
-- Rebuilds the wheel pages from stored data.
local function CleanPages(pages, scenes)
    local clean = {}
    for _, page in ipairs(type(pages) == "table" and pages or {}) do
        if type(page) == "table" and #clean < L.Db.MAX_WHEEL_PAGES then
            local slots = {}
            for slot = 1, L.Db.WHEEL_SLOTS do
                slots[slot] = Text(page[slot], 64) or ""
            end

            clean[#clean + 1] = slots
        end
    end

    if #clean == 0 then
        clean[1] = DefaultPage(scenes)
    end

    return clean
end

-- input: a stored set of scenes and triggers
-- output: a clean copy, or nil when it is not a table
-- Rebuilds a set from scratch.
local function CleanSet(set)
    -- Starting from scratch means a hand edited or damaged file cannot leave
    -- a value of the wrong type for the rest of the addon to trip over.
    if type(set) ~= "table" then
        return nil
    end

    local clean, taken = { scenes = {}, triggers = {} }, {}

    for _, scene in ipairs(type(set.scenes) == "table" and set.scenes or {}) do
        clean.scenes[#clean.scenes + 1] = CleanScene(scene, taken)
    end

    for _, trigger in ipairs(type(set.triggers) == "table" and set.triggers or {}) do
        clean.triggers[#clean.triggers + 1] = CleanTrigger(trigger)
    end

    clean.wheelPages = CleanPages(set.wheelPages, clean.scenes)

    return clean
end

-- input: stored settings
-- output: settings with every key present and of the right type
-- Rebuilds the settings, falling back to the default for any bad value.
local function CleanSettings(stored)
    local settings = {}

    for key, default in pairs(SETTINGS_DEFAULT) do
        local value
        if type(stored) == "table" then
            value = stored[key]
        end

        if type(value) == type(default) then
            settings[key] = value
        else
            settings[key] = L.Util.DeepCopy(default)
        end
    end

    settings.primeTimeout = Number(settings.primeTimeout, 3, 60, 8)
    settings.globalTriggerGap = Number(settings.globalTriggerGap, 0, 300, 10)
    settings.wheelScale = Number(settings.wheelScale, 0.5, 2, 1)

    return settings
end

-- input: nothing
-- output: nothing
-- Cleans the saved variables, seeding the starter pack on a first install.
function L.Db.Load()
    local stored = SpeakEasyDB
    SpeakEasyDB = CleanSet(stored) or CleanSet(Starter())
    SpeakEasyDB.version = L.Db.VERSION
    SpeakEasyDB.settings = CleanSettings(type(stored) == "table" and stored.settings)

    local character = type(SpeakEasyCharDB) == "table" and SpeakEasyCharDB or {}
    local characterSet = type(character.scenes) == "table" and CleanSet(character) or nil
    SpeakEasyCharDB = characterSet or {}
    SpeakEasyCharDB.useOwn = characterSet ~= nil and character.useOwn == true
end

-- input: nothing
-- output: the active set of scenes and triggers
-- Returns this character's own set when it uses one, else the account set.
function L.Db.Set()
    if SpeakEasyCharDB.useOwn then
        return SpeakEasyCharDB
    end

    return SpeakEasyDB
end

-- input: nothing
-- output: the account wide settings
-- Returns the settings table.
function L.Db.Settings()
    return SpeakEasyDB.settings
end

-- input: nothing
-- output: true when this character uses its own set
-- Reports whether the character set is active.
function L.Db.UsesCharacterSet()
    return SpeakEasyCharDB.useOwn == true
end

-- input: true to give this character its own set, false for the account set
-- output: nothing
-- Switches sets, copying the account set the first time a character gets its own.
function L.Db.SetCharacterSet(on)
    if on and not SpeakEasyCharDB.scenes then
        SpeakEasyCharDB.scenes = L.Util.DeepCopy(SpeakEasyDB.scenes)
        SpeakEasyCharDB.triggers = L.Util.DeepCopy(SpeakEasyDB.triggers)
        SpeakEasyCharDB.wheelPages = L.Util.DeepCopy(SpeakEasyDB.wheelPages)
    end

    SpeakEasyCharDB.useOwn = on and true or false
    L.Play.ResetAll()
end

-- input: a scene id or name, any case
-- output: the scene and its index, or nil
-- Looks up a scene in the active set by id or name.
function L.Db.FindScene(key)
    if type(key) ~= "string" then
        return nil
    end

    local lower = key:lower()
    for index, scene in ipairs(L.Db.Set().scenes) do
        if scene.id == lower or scene.name:lower() == lower then
            return scene, index
        end
    end
end

-- input: a proposed name and the scene being renamed, if any
-- output: the trimmed name, or nil and the reason it cannot be used
-- Checks a scene name is present, short enough and not already taken.
function L.Db.CheckName(name, except)
    name = strtrim(tostring(name or ""))
    if name == "" then
        return nil, L.Text.ERR_NAME_EMPTY
    end

    if #name > L.Db.MAX_NAME then
        return nil, L.Text.ERR_NAME_LONG
    end

    for _, scene in ipairs(L.Db.Set().scenes) do
        if scene ~= except and scene.name:lower() == name:lower() then
            return nil, L.Text.ERR_NAME_TAKEN
        end
    end

    return name
end

-- input: nothing
-- output: a table with every scene id in the active set as a key
-- Collects the ids already in use.
local function TakenIds()
    local taken = {}
    for _, scene in ipairs(L.Db.Set().scenes) do
        taken[scene.id] = true
    end

    return taken
end

-- input: a name and optionally a scene to copy
-- output: the new scene, or nil and the reason
-- Adds a scene at the end of the list.
function L.Db.AddScene(name, copyFrom)
    local valid, err = L.Db.CheckName(name)
    if not valid then
        return nil, err
    end

    local scene = copyFrom and L.Util.DeepCopy(copyFrom)
        or { icon = L.Db.DEFAULT_ICON, channel = "SAY", cooldown = 2, enabled = true, lines = {} }
    scene.name = valid
    scene.id = UniqueId(valid, TakenIds())
    scene.macroName = nil

    local scenes = L.Db.Set().scenes
    scenes[#scenes + 1] = scene
    L.Db.PlaceOnWheel(scene.id)

    return scene, #scenes
end

-- input: a scene
-- output: the copy and its index
-- Copies a scene under the first free "<name> copy" name.
function L.Db.DuplicateScene(scene)
    local base = L.Util.Cut(scene.name, L.Db.MAX_NAME - 7) .. " " .. L.Text.COPY_SUFFIX
    local name, number = base, 1
    while not L.Db.CheckName(name) do
        number = number + 1
        name = base .. " " .. number
    end

    return L.Db.AddScene(name, scene)
end

-- input: a scene and a new name
-- output: the scene, or nil and the reason
-- Renames a scene. Its id, and so every bar button, stays the same.
function L.Db.RenameScene(scene, name)
    local valid, err = L.Db.CheckName(name, scene)
    if not valid then
        return nil, err
    end

    scene.name = valid
    L.Macro.Sync(scene)

    return scene
end

-- input: nothing
-- output: the active set's wheel pages
-- Returns the wheel pages of the active set.
function L.Db.WheelPages()
    return L.Db.Set().wheelPages
end

-- input: a scene id or emote slot
-- output: nothing
-- Puts a new scene in the first empty wheel slot, if there is one.
function L.Db.PlaceOnWheel(value)
    for _, page in ipairs(L.Db.WheelPages()) do
        for slot = 1, L.Db.WHEEL_SLOTS do
            if page[slot] == "" then
                page[slot] = value
                return
            end
        end
    end
end

-- input: a page number, a slot number, and a scene id, emote slot or nil to empty it
-- output: nothing
-- Sets or empties one wheel slot.
function L.Db.SetWheelSlot(pageIndex, slot, value)
    local page = L.Db.WheelPages()[pageIndex]
    if page and slot >= 1 and slot <= L.Db.WHEEL_SLOTS then
        page[slot] = value or ""
    end
end

-- input: how many pages the wheel should have
-- output: the page count after clamping
-- Adds empty pages at the end, or drops pages from the end.
function L.Db.SetWheelPageCount(count)
    local pages = L.Db.WheelPages()
    count = math.max(1, math.min(L.Db.MAX_WHEEL_PAGES, math.floor(count)))

    while #pages < count do
        local page = {}
        for slot = 1, L.Db.WHEEL_SLOTS do
            page[slot] = ""
        end

        pages[#pages + 1] = page
    end

    while #pages > count do
        table.remove(pages)
    end

    return count
end

-- input: a scene index
-- output: nothing
-- Removes a scene and forgets its line rotation.
function L.Db.DeleteScene(index)
    local scene = table.remove(L.Db.Set().scenes, index)
    if scene then
        L.Play.ResetBag(scene.id)
    end
end

-- input: a scene, a line index or nil for a new line, and the line's fields
-- output: the line's index, or nil when the line is empty
-- Cleans and stores a line, replacing the one at the index or adding it.
function L.Db.SaveLine(scene, index, line)
    local clean = CleanLine(line)
    if not clean then
        return nil
    end

    if index and scene.lines[index] then
        scene.lines[index] = clean
    else
        scene.lines[#scene.lines + 1] = clean
        index = #scene.lines
    end

    -- Every change to a scene's lines starts its rotation again.
    L.Play.ResetBag(scene.id)

    return index
end

-- input: a scene and a line index
-- output: nothing
-- Removes a line and restarts the scene's rotation.
function L.Db.DeleteLine(scene, index)
    table.remove(scene.lines, index)
    L.Play.ResetBag(scene.id)
end

-- input: a scene, a line index and whether it is enabled
-- output: nothing
-- Turns a line on or off and restarts the scene's rotation.
function L.Db.SetLineEnabled(scene, index, enabled)
    if scene.lines[index] then
        scene.lines[index].enabled = enabled and true or false
        L.Play.ResetBag(scene.id)
    end
end

-- input: nothing
-- output: a trigger with the default chance and cooldown
-- Builds a new trigger pointing at the first scene.
function L.Db.NewTrigger()
    local first = L.Db.Set().scenes[1]

    return {
        event = "ENTER_COMBAT",
        sceneId = first and first.id or "",
        chance = 30,
        cooldown = 60,
        enabled = true,
        options = { threshold = 30 },
    }
end

-- input: a trigger index or nil for a new one, and the trigger's fields
-- output: the trigger's index, or nil when it is not valid
-- Cleans and stores a trigger, replacing the one at the index or adding it.
function L.Db.SaveTrigger(index, trigger)
    local clean = CleanTrigger(trigger)
    if not clean then
        return nil
    end

    local triggers = L.Db.Set().triggers
    if index and triggers[index] then
        triggers[index] = clean
    else
        triggers[#triggers + 1] = clean
        index = #triggers
    end

    return index
end

-- input: a trigger index
-- output: nothing
-- Removes a trigger.
function L.Db.DeleteTrigger(index)
    table.remove(L.Db.Set().triggers, index)
end
