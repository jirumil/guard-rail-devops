output "container_registry_login_server" {
  value       = data.azurerm_container_registry.main.login_server # <-- Changed to data.
  description = "The URL of the container registry"
}

output "api_url" {
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
  description = "The public URL of the API gateway"
}

output "frontend_url" {
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
  description = "The public URL of the frontend application"
}

output "resource_group" {
  value       = data.azurerm_resource_group.main.name
  description = "The name of the resource group"
}