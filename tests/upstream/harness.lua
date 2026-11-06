-- Usage: lua5.1 harness.lua <SpeakEasy_Db.lua> <SpeakEasy.lua to load>
-- Loads a SavedVariables file, runs SpeakEasy's L.Db.Load and prints both
-- the stored and the cleaned tables in a stable form for comparison.
local dbFile, savedFile = arg[1], arg[2]

function strtrim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

local L = { Util = {}, Text = { NEW_SCENE = "New scene" } }

function L.Util.DeepCopy(value)
    if type(value) ~= "table" then return value end
    local copy = {}
    for k, v in pairs(value) do copy[k] = L.Util.DeepCopy(v) end
    return copy
end

-- Same as SpeakEasy_Util.lua's L.Util.Cut.
function L.Util.Cut(text, limit)
    if #text <= limit then return text end
    local cut = text:sub(1, limit)
    local lead = cut:find("[\192-\255][\128-\191]*$")
    if lead then
        local first = cut:byte(lead)
        local size = first >= 240 and 4 or first >= 224 and 3 or 2
        if #cut - lead + 1 < size then cut = cut:sub(1, lead - 1) end
    end
    return cut
end

local chunk = assert(loadfile(savedFile))
setfenv(chunk, _G)
chunk()
assert(loadfile(dbFile))("SpeakEasy", L)

local function dump(value)
    if type(value) ~= "table" then
        return type(value) == "string" and string.format("%q", value) or tostring(value)
    end
    local keys = {}
    for k in pairs(value) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local out = {}
    for _, k in ipairs(keys) do out[#out + 1] = tostring(k) .. "=" .. dump(value[k]) end
    return "{" .. table.concat(out, ",") .. "}"
end

local function report(label, sets)
    for _, name in ipairs({ "account", "character" }) do
        local set = sets[name] or {}
        for _, key in ipairs({ "scenes", "triggers", "wheelPages", "useOwn", "settings" }) do
            print(label .. " " .. name .. "." .. key .. " " .. dump(set[key]))
        end
    end
end

local before = { account = L.Util.DeepCopy(SpeakEasyDB), character = L.Util.DeepCopy(SpeakEasyCharDB) }
L.Db.Load()
report("BEFORE", before)
report("AFTER", { account = SpeakEasyDB, character = SpeakEasyCharDB })
