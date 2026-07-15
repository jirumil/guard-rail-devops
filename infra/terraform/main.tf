# ---- Resource Group (Data Source) ----
data "azurerm_resource_group" "main" {
  name = "rg-guardrail-dev-app"
}

# ---- Container Registry (Data Source) ----
data "azurerm_container_registry" "main" {
  name                = "guardrailcrdev2026v4"
  resource_group_name = data.azurerm_resource_group.main.name
}

# ---- Log Analytics (Data Source) ----
data "azurerm_log_analytics_workspace" "main" {
  name                = "log-guardrail-dev-v3"
  resource_group_name = data.azurerm_resource_group.main.name
}