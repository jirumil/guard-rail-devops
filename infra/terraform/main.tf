resource "azurerm_resource_group" "main" {
  name     = "rg-guardrail-dev-app"
  location = "southeastasia"
}

# ---- Import Blocks to bring existing infra into state ----
import {
  to = azurerm_resource_group.main
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app"
}

import {
  to = azurerm_container_registry.main
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.ContainerRegistry/registries/guardrailcrdev2026"
}

import {
  to = azurerm_log_analytics_workspace.main
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.OperationalInsights/workspaces/log-guardrail-dev"
}

# ---- Import Blocks for the Container Apps ----
import {
  to = azurerm_container_app.redis
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.App/containerApps/guardrail-redis"
}

import {
  to = azurerm_container_app.api
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.App/containerApps/guardrail-api"
}

import {
  to = azurerm_container_app.worker
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.App/containerApps/guardrail-worker"
}

import {
  to = azurerm_container_app.frontend
  id = "/subscriptions/039f6f22-d707-42bb-8d89-0125f1069e3f/resourceGroups/rg-guardrail-dev-app/providers/Microsoft.App/containerApps/guardrail-frontend"
}

# ---- Container Registry ----
resource "azurerm_container_registry" "main" {
  name                = "guardrailcrdev2026"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
}

# ---- Reference the V2 Registry for Image Pulls ----
data "azurerm_container_registry" "v2" {
  name                = "guardrailcrdev2026v2"
  resource_group_name = azurerm_resource_group.main.name
}

# ---- Log Analytics ----
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-guardrail-dev"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}