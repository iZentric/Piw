-- Custom store category for the DT pack (FS25 port of Dajoor's categorizer).
Categorizer = {}
Categorizer.modFolder = g_currentModDirectory
Categorizer.modDescFile = Categorizer.modFolder .. "modDesc.xml"

local function registerCategories()
    if not fileExists(Categorizer.modDescFile) then
        g_logManager:xmlWarning(Categorizer.modDescFile, "*** Categorizer: no modDesc found!")
        return
    end
    local modDescFile = loadXMLFile("modDesc", Categorizer.modDescFile)
    local i = 0
    while i < 10 do
        local ndx = string.format("modDesc.newcategory(%d)", i)
        if not hasXMLProperty(modDescFile, ndx) then break end
        local name = getXMLString(modDescFile, ndx .. "#name")
        if name == nil or name == "" then break end
        name = name:upper()
        if g_storeManager:getCategoryByName(name) ~= nil then
            g_logManager:xmlWarning(modDescFile, "*** Categorizer: category '%s' already exists!", tostring(name))
            break
        end
        local title = getXMLString(modDescFile, ndx .. "#title")
        if title == nil or title == "" then title = name end
        title = g_i18n:hasText(title) and g_i18n:getText(title) or title:upper()
        local cattype = getXMLString(modDescFile, ndx .. "#type")
        if cattype == nil or cattype == "" then cattype = "VEHICLE" end
        cattype = cattype:upper()
        local img = getXMLString(modDescFile, ndx .. "#img")
        local ok, err = pcall(function()
            g_storeManager:addCategory(name, title, img, cattype, Categorizer.modFolder)
        end)
        if not ok then
            g_logManager:xmlWarning(modDescFile, "*** Categorizer: could not add '%s' (%s)", tostring(name), tostring(err))
        end
        i = i + 1
    end
    delete(modDescFile)
end

local function onMissionLoaded()
    registerCategories()
end

g_messageCenter:subscribe(MessageType.MISSION_LOADED, onMissionLoaded)
