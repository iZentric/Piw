-- Allows using:
-- designMaterial4Configurations up to designMaterial49Configurations and 
-- design9Configurations up to design49Configurations

MoreDesignConfigs = {
  prerequisitesPresent = function()
    return true
  end
}

function MoreDesignConfigs.initSpecialization()
  -- Increase max configuration options to 256
  ConfigurationUtil.SEND_NUM_BITS = 8

  local schema = Vehicle.xmlSchema
  for i = 9, 49 do
    g_configurationManager:addConfigurationType(string.format("design%d", i), g_i18n:getText("configuration_design"), nil, nil, ConfigurationUtil.getConfigColorSingleItemLoad, ConfigurationUtil.getConfigColorPostLoad, ConfigurationUtil.SELECTOR_MULTIOPTION)
		ConfigurationUtil.registerColorConfigurationXMLPaths(schema, string.format("design%d", i))
		ObjectChangeUtil.registerObjectChangeXMLPaths(schema, string.format("vehicle.design%dConfigurations.design%dConfiguration(?)", i, i))
	end

  schema:setXMLSpecializationType("BaseMaterial")
	
  for j = 4, 49 do
    g_configurationManager:addConfigurationType(string.format("designMaterial%d", j), g_i18n:getText("configuration_designColor"), nil, nil, ConfigurationUtil.getConfigColorSingleItemLoad, ConfigurationUtil.getConfigColorPostLoad, ConfigurationUtil.SELECTOR_COLOR)
    BaseMaterial.registerBaseMaterialConfigurationsXMLPaths(schema, string.format("designMaterial%d", j))
    ConfigurationUtil.registerColorConfigurationXMLPaths(schema, string.format("designMaterial%d", j))
    ObjectChangeUtil.registerObjectChangeXMLPaths(schema, string.format("vehicle.designMaterial%dConfigurations.designMaterial%dConfiguration(?)", j, j))
  end
  
	schema:setXMLSpecializationType()
end

function MoreDesignConfigs.registerEventListeners(vehicleType)
	SpecializationUtil.registerEventListener(vehicleType, "onLoad", MoreDesignConfigs)
end

function MoreDesignConfigs:onLoad(savegame)
  for i = 9, 49 do
    local name = string.format("design%d", i)

    if self.configurations[name] ~= nil then
      ObjectChangeUtil.updateObjectChanges(self.xmlFile, string.format("vehicle.design%dConfigurations.design%dConfiguration", i, i), self.configurations[name], self.components, self)
    end
  end

  for j = 4, 49 do
    local name = string.format("designMaterial%d", j)

    if self.configurations[name] ~= nil then
      self:applyBaseMaterialConfiguration(self.xmlFile, string.format("designMaterial%d", j), self.configurations[name])
      ObjectChangeUtil.updateObjectChanges(self.xmlFile, string.format("vehicle.designMaterial%dConfigurations.designMaterial%dConfiguration", j, j), self.configurations[name], self.components, self)
    end
  end
end