-- Lampovo Project ^ω^ Average Enjoyer

averageMaterial = {
    MOD_NAME = g_currentModName,
    MOD_DIR = g_currentModDirectory
}
-- Увеличиваем лимит конфигураций
ConfigurationUtil.SEND_NUM_BITS = 8

-- Возвращаем конфигурации baseMaterial и designMaterial
local function inj_vehicle_init()
    g_vehicleConfigurationManager:addConfigurationType("baseMaterial", g_i18n:getText("configuration_baseColor"), nil, VehicleConfigurationItemColor)
    g_vehicleConfigurationManager:addConfigurationType("designMaterial", g_i18n:getText("configuration_designColor"), nil, VehicleConfigurationItemColor)
    for i = 2, 64 do
        g_vehicleConfigurationManager:addConfigurationType(string.format("designMaterial%d", i), g_i18n:getText("configuration_designColor"), nil, VehicleConfigurationItemColor)
    end
end

Vehicle.init = Utils.appendedFunction(Vehicle.init, inj_vehicle_init)


-- Востановление порезанной специализации BaseMaterial
function inj_baseMaterial_prerequisitesPresent(specializations)
    return true
end

BaseMaterial.prerequisitesPresent = Utils.overwrittenFunction(BaseMaterial.prerequisitesPresent, inj_baseMaterial_prerequisitesPresent)

-- Регистрация утраченных путей BaseMaterial
function inj_baseMaterial_initSpecialization()
    local schema = Vehicle.xmlSchema

    schema:setXMLSpecializationType("BaseMaterial")
    local basePath = "vehicle.baseMaterial.material"
    schema:register(XMLValueType.STRING, basePath .. "(?)#name", "Material name")
    schema:register(XMLValueType.NODE_INDEX, basePath .. "(?)#baseNode", "Material base node")
    schema:register(XMLValueType.STRING, basePath .. "(?).shaderParameter(?)#name", "Shader parameter name") -- сейчас не используется
    schema:register(XMLValueType.INT, basePath .. "(?).shaderParameter(?)#material", "Material value") -- сейчас не используется
    schema:setXMLSpecializationType()
end

BaseMaterial.initSpecialization = Utils.overwrittenFunction(BaseMaterial.initSpecialization, inj_baseMaterial_initSpecialization)

-- Востановление записи таблицы baseMaterials
function inj_baseMaterial_onLoad(self, superfunc, savegame)
    -- Вывод предупреждений об устаревшем пути vehicle.%sConfigurations.material(?)#name смененном на ...material(?)#materialSlutName
    for configName, configData in pairs(self.configurations) do
        local basePath = string.format("vehicle.%sConfigurations", configName)
        local numMaterials = self.xmlFile:getNumOfElements(basePath .. ".material")

        for i = 0, numMaterials - 1 do
            local oldPath = string.format("%s.material(%d)#name", basePath, i)
            local newPath = string.format("%s.material(%d)#materialSlotName", basePath, i)
            XMLUtil.checkDeprecatedXMLElements(self.xmlFile, oldPath, newPath)
        end
    end

    local spec = self.spec_baseMaterial
    spec.baseMaterials = {}
    spec.nameToMaterial = {}

    local function loadBaseMaterials(xmlFile, baseKey, components, i3dMappings)
        local materials = {}

        xmlFile:iterate(baseKey, function(i, key)
            local name = xmlFile:getValue(key .. "#name")
            local baseNode = xmlFile:getValue(key .. "#baseNode", nil, components, i3dMappings)
            local materialId = getMaterial(baseNode, 0)

            if name ~= nil and baseNode ~= nil and materialId ~= 0 then
                local material = {
                    name = name,
                    baseNode = baseNode,
                    materialId = materialId,
                    shaderParameters = {}
                }

                local i = 0
                while true do
                    local parameterKey = string.format("%s.shaderParameter(%d)", key, i)
                    if not xmlFile:hasProperty(parameterKey) then
                        break
                    end

                    local paramName = xmlFile:getValue(parameterKey .. "#name")
                    if paramName ~= nil then
                        table.insert(material.shaderParameters, { name = paramName })
                    end

                    i = i + 1
                end

                table.insert(materials, material)
            else
                Logging.xmlWarning(self.xmlFile, "Missing baseNode for base material '%s'", key)
            end
        end)

        return materials
    end

    spec.baseMaterials = loadBaseMaterials(self.xmlFile, "vehicle.baseMaterial.material", self.components, self.i3dMappings)

    for i = 1, #spec.baseMaterials do
        local baseMaterial = spec.baseMaterials[i]
        spec.nameToMaterial[baseMaterial.name] = baseMaterial
    end
end

BaseMaterial.onLoad = Utils.overwrittenFunction(BaseMaterial.onLoad, inj_baseMaterial_onLoad)



-- Добавление возможности указать материал для цвета
local function inj_vehicleConfigurationItemColor_loadFromXML(self, superfunc, xmlFile, basekey, configKey, baseDirectory, customEnvironment)
    superfunc(self, xmlFile, basekey, configKey, baseDirectory, customEnvironment)

    local material = xmlFile:getValue(configKey .. "#material", nil, true)
    if material ~= nil then
        self.color[4] = material
    end
    return true
end

VehicleConfigurationItemColor.loadFromXML = Utils.overwrittenFunction(VehicleConfigurationItemColor.loadFromXML, inj_vehicleConfigurationItemColor_loadFromXML)

-- Регистрация пути material для указания материала
local function inj_vehicleConfigurationItemColor_registerXMLPaths(schema, rootPath, configPath)
    schema:register(XMLValueType.INT, configPath .. "#material", "Material value", 0)
end

VehicleConfigurationItemColor.registerXMLPaths = Utils.appendedFunction(VehicleConfigurationItemColor.registerXMLPaths, inj_vehicleConfigurationItemColor_registerXMLPaths)



-- Установка цвета RGB или RGBM (с материалом для shaderParameter)
local function inj_vehicleMaterial_setColor(self, superfunc, color, g, b)
    if color == nil then
        return
    elseif type(color) == "table" then
        local r, g, b, mat = color[1], color[2], color[3], color[4]
        if mat ~= nil then
            self.colorScale = { r, g, b, mat }
        else
            self.colorScale = { r, g, b }
        end
    else
        self.colorScale = { color, g or 1.0, b or 1.0 }
    end
end

VehicleMaterial.setColor = Utils.overwrittenFunction(VehicleMaterial.setColor, inj_vehicleMaterial_setColor)

-- Добавление возможности указать параметр шейдер для применения цвета, а также получение таблицы baseMaterials
local function inj_vehicleMaterial_loadFromXML(self, superfunc, xmlFile, key, customEnvironment, baseMaterials)
    local returnValue = superfunc(self, xmlFile, key, customEnvironment)
    local spec = self.spec_baseMaterial
    if returnValue then
        -- self.baseMaterials = baseMaterials
        self.shaderParameter = xmlFile:getValue(key .. "#shaderParameter")
        local material = xmlFile:getValue(key .. ".colorScale#material", nil, true)
        if material ~= nil and self.colorScale ~= nil then
            self.colorScale[4] = material
        end
    end

    return returnValue
end

VehicleMaterial.loadFromXML = Utils.overwrittenFunction(VehicleMaterial.loadFromXML, inj_vehicleMaterial_loadFromXML)

-- Добавлено определение baseMaterials в VehicleMaterial
local function inj_vehicleMaterial_applyToVehicle(self, superfunc, vehicle, targetMaterialSlotName)
	local spec = vehicle.spec_baseMaterial
	self.baseMaterials = spec.baseMaterials
	local success = false
	for _, component in ipairs(vehicle.components) do
		success = self:apply(component.node, targetMaterialSlotName) or success
	end
	return success
end

VehicleMaterial.applyToVehicle = Utils.overwrittenFunction(VehicleMaterial.applyToVehicle, inj_vehicleMaterial_applyToVehicle)

-- Добавлено возможность применения цвета на материал объекта указаного в baseMaterial.material#baseNode
local function inj_vehicleMaterial_apply(self, superfunc, node, targetMaterialSlotName, colorOnly)
    local success = false
    local targetSlotName = targetMaterialSlotName or self.targetMaterialSlotName

    if getHasClassId(node, ClassIds.SHAPE) then
        for i = 1, getNumOfMaterials(node) do
            local materialIndex = i - 1
            local currentSlotName = getMaterialSlotName(node, materialIndex)

            if currentSlotName == targetSlotName or targetSlotName == nil then
                self:applyToMaterial(node, materialIndex, colorOnly)
                success = true
            end
        end

        if not success and self.baseMaterials ~= nil then
            local nodeMaterialId = getMaterial(node, 0)
            if nodeMaterialId ~= 0 then
                for _, baseMaterial in ipairs(self.baseMaterials) do
                    local baseNodeMaterialId = getMaterial(baseMaterial.baseNode, 0)
                    if nodeMaterialId ~= 0 then
                        if baseMaterial.name == targetSlotName and baseNodeMaterialId == nodeMaterialId then
                            for i = #baseMaterial.shaderParameters, 1, -1 do
                                local parameter = baseMaterial.shaderParameters[i]
                                if parameter.name == self.shaderParameter then
                                    local _, _, _, currentMaterial = getShaderParameter(node, self.shaderParameter)
                                    local material = self.colorScale[4] or currentMaterial

                                    setShaderParameter(node, self.shaderParameter, self.colorScale[1], self.colorScale[2], self.colorScale[3], material, false, 0)
                                    success = true
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    for i = 0, getNumOfChildren(node) - 1 do
        local child = getChildAt(node, i)
        success = self:apply(child, targetSlotName, colorOnly) or success
    end

    return success
end

VehicleMaterial.apply = Utils.overwrittenFunction(VehicleMaterial.apply, inj_vehicleMaterial_apply)

-- Регистрация пути shaderParameter для указания параметра шейдера (например colorMat) для применения цвета
local function inj_vehicleMaterial_registerXMLPaths(schema, basePath)
    schema:register(XMLValueType.STRING, basePath .. "#shaderParameter", "Material shader parameter name")
    schema:register(XMLValueType.INT, basePath .. ".colorScale#material", "Material value for colorScale if it should not be used from configuration", 0)
end

VehicleMaterial.registerXMLPaths = Utils.appendedFunction(VehicleMaterial.registerXMLPaths, inj_vehicleMaterial_registerXMLPaths)