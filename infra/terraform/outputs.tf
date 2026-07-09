output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "api_url" {
  value = "https://${azurerm_container_app.api.latest_revision_fqdn}"
}

output "frontend_url" {
  value = "https://${azurerm_container_app.frontend.latest_revision_fqdn}"
}

output "resource_group" {
  value = azurerm_resource_group.main.name
}
