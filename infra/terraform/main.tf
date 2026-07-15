resource "azurerm_resource_group" "main" {
  name     = "rg-guardrail-dev-app"
  location = "southeastasia"
}

# Add the import block here:
import {
  to = azurerm_resource_group.main
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app"
}

# ---- Container Registry ----
resource "azurerm_container_registry" "main" {
  name                = "guardrailcrdev2026v2" # <-- Change to v2
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
}

# ---- Blob Storage ----
# NOTE: GuardRail's actual storage account (stguardrailscans) is
# provisioned manually in the portal and referenced via the
# data "azurerm_storage_account" "guardrail" block in dependencies.tf —
# only the worker touches storage.py, and it already points there. This
# Terraform-managed storage account was leftover from an earlier
# iteration and has been removed to avoid provisioning a second, unused,
# billable storage account.

# ---- Log Analytics ----
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-guardrail-dev"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}