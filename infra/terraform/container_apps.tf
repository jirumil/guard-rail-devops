data "azurerm_container_app_environment" "main" {
  name                = "cae-guardrail-dev"
  resource_group_name = azurerm_resource_group.main.name
}

# ---- Redis as a Container App (avoids Azure Cache for Redis cost) ----
resource "azurerm_container_app" "redis" {
  name                         = "${var.project}-redis"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  secret {
    name  = "redis-password"
    value = random_password.redis.result
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name    = "redis"
      image   = "redis:7.4-alpine"
      # FIXED: Placed back inside container block, wrapped in strict quotes
      cpu     = "0.25"
      memory  = "0.5Gi"
      command = ["redis-server", "--requirepass", "$(REDIS_PASSWORD)"]

      env {
        name        = "REDIS_PASSWORD"
        secret_name = "redis-password"
      }
    }
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
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
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
    min_replicas = 1
    max_replicas = 3

    container {
      name  = "api"
      image = "${data.azurerm_container_registry.v2.login_server}/guardrail-api:${var.api_image_tag}"
      # FIXED: Placed back inside container block, wrapped in strict quotes
      cpu     = "0.5"
      memory  = "1.0Gi"

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
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
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
    min_replicas = 1
    max_replicas = 2

    container {
      name  = "frontend"
      image = "${azurerm_container_registry.main.login_server}/guardrail-frontend:${var.frontend_image_tag}"
      # FIXED: Placed back inside container block, wrapped in strict quotes
      cpu    = "0.25"
      memory = "0.5Gi"

      env {
        name  = "API_BASE_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }
    }
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