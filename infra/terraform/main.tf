# ---- Resource Group (Data Source) ----
# Using a data block because the resource group already exists in Azure.
data "azurerm_resource_group" "main" {
  name = "rg-guardrail-dev-app"
}

# ---- Container Registry ----
resource "azurerm_container_registry" "main" {
  name                = "guardrailcrdev2026v4" # <-- Changed from v3 to v4
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
}

# ---- Log Analytics ----
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-guardrail-dev-v3" # <-- Changed from v2 to v3
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}