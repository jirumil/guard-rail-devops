# 1. Changed to a data block to read the existing environment
data "azurerm_container_app_environment" "main" {
  name                = "cae-guardrail-dev"
  resource_group_name = data.azurerm_resource_group.main.name
}

# ---- Redis as a Container App ----
resource "azurerm_container_app" "redis" {
  name                         = "${var.project}-redis"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id # <-- Updated reference
  revision_mode                = "Single"

  secret {
    name  = "redis-password"
    value = random_password.redis.result
  }

  template {
    container {
      name    = "redis"
      image   = "redis:7.4-alpine"
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["redis-server", "--requirepass", "$(REDIS_PASSWORD)"]

      env {
        name        = "REDIS_PASSWORD"
        secret_name = "redis-password"
      }
    }
    min_replicas = 1
    max_replicas = 1
  }

  ingress {
    external_enabled = false  
    target_port      = 6379   
    exposed_port     = 6379   
    transport        = "tcp"  
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---- API ----
resource "azurerm_container_app" "api" {
  name                         = "${var.project}-api"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id # <-- Updated reference
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  template {
    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/guardrail-api:${var.api_image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "GUNICORN_CMD_ARGS"
        value = "--timeout 120 --keep-alive 10 --workers 2"
      }

      env {
        name  = "REDIS_URL"
        value = "redis://:${random_password.redis.result}@${azurerm_container_app.redis.name}:6379/0"
      }
      liveness_probe {
        transport               = "HTTP"
        path                    = "/healthz"
        port                    = 5000
        initial_delay           = 45  
        timeout                 = 10  
        failure_count_threshold = 3
      }
    }
    min_replicas = 1
    max_replicas = 3
  }

  ingress {
    external_enabled = true
    target_port      = 5000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---- Frontend ----
resource "azurerm_container_app" "frontend" {
  name                         = "${var.project}-frontend"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id # <-- Updated reference
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  template {
    container {
      name   = "frontend"
      image  = "${azurerm_container_registry.main.login_server}/guardrail-frontend:${var.frontend_image_tag}"
      cpu    = "0.25"
      memory = "0.5Gi"

      env {
        name  = "API_BASE_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }
    }
    min_replicas = 1
    max_replicas = 2
  }

  ingress {
    external_enabled = true
    target_port      = 80
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}