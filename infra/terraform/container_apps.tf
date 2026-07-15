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
    external_enabled = false  # Keeps it locked inside your private cluster environment
    target_port      = 6379   # The port Redis listens to inside its own container
    exposed_port     = 6379   # FIXED: Allocates a dedicated internal proxy port for your architecture mesh
    transport        = "tcp"  # FIXED: Reverted back to native TCP
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
    container {
      name   = "api"
      image  = "${data.azurerm_container_registry.v2.login_server}/guardrail-api:${var.image_tag}" 
      cpu    = "0.5"
      memory = "1.0Gi"

      # FIXED: Added Gunicorn tuning configurations to stop it killing its own workers early
      env {
        name  = "GUNICORN_CMD_ARGS"
        value = "--timeout 120 --keep-alive 10 --workers 2"
      }

      # REDEPLOY_TRICK removed — was a cache-busting workaround for the
      # api_image_tag defaulting to "latest" (a mutable tag Terraform
      # can't diff). Now that api_image_tag has no default and is
      # validated to reject "latest" outright (see variables.tf), a real
      # tag change is guaranteed on every deploy — this workaround is no
      # longer structurally possible to need.
      env {
        name  = "REDIS_URL"
        value = "redis://:${random_password.redis.result}@${azurerm_container_app.redis.name}:6379/0"
      }
      liveness_probe {
        transport               = "HTTP"
        path                    = "/healthz"
        port                    = 5000
        initial_delay           = 45  # FIXED: Prevents premature platform termination
        timeout                 = 10  # FIXED: Gives breathing room for slow responses
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