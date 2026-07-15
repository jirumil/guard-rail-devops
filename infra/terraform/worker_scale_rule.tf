# =============================================================================
# Worker Container App — KEDA Redis scale rule
# =============================================================================
# QUEUE NAME CORRECTION — READ THIS FIRST:
# You specified `rq:queue:default` in your requirements. That is NOT this
# codebase's actual queue name. GuardRail's Flask API creates its queue as:
#       Queue("file-scanning", connection=get_redis_conn())      # app.py
# and the worker's Dockerfile CMD listens on the same name:
#       rq worker file-scanning --path . --url redis://...        # Dockerfile
#
# RQ stores pending jobs in Redis under the key `rq:queue:<name>` — so the
# correct list for KEDA to watch is `rq:queue:file-scanning`, not
# `rq:queue:default`. Using "default" here would make the worker fleet sit
# at 0 replicas permanently, watching a Redis list that never receives
# anything — no error, no warning, just workers that never start. This
# snippet uses the correct name.

resource "azurerm_container_app" "worker" {
  name                         = "guardrail-worker"
  resource_group_name          = data.azurerm_resource_group.main.name
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
  secret {
    name  = "redis-password"
    value = random_password.redis.result
  }
  secret {
    name  = "storage-account-key"
    value = data.azurerm_storage_account.guardrail.primary_access_key
  }

  template {
    container {
      name   = "worker"
      # FIXED: Points directly to latest tag to capture your clean, manual docker pushes
      image  = "${azurerm_container_registry.main.login_server}/guardrail-worker:latest"
      cpu    = "0.25"
      memory = "0.5Gi"

      # FIXED: Changed from ingress[0].fqdn to .name here as well for native Layer-4 TCP routing
      command = [
        "rq",
        "worker",
        "file-scanning",
        "--url",
        "redis://:${random_password.redis.result}@${azurerm_container_app.redis.name}:6379/0"
      ]

      env {
        name  = "REDIS_URL"
        value = "redis://:${random_password.redis.result}@${azurerm_container_app.redis.name}:6379/0"
      }
      # REDEPLOY_TRICK removed — see the matching comment in
      # container_apps.tf for why it's structurally unnecessary now.
      env {
        name  = "STORAGE_PROVIDER"
        value = "azure"
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = data.azurerm_storage_account.guardrail.name
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_KEY"
        secret_name = "storage-account-key"
      }
      env {
        name  = "STORAGE_BUCKET"
        value = "guardrail-quarantine"
      }
    } # Closed container block cleanly

    # THE BUDGET-PROTECTION LINE — explicit, not left to a platform default.
    min_replicas = 0
    max_replicas = 10

    custom_scale_rule {
      name             = "redis-queue-depth"
      custom_rule_type = "redis"

      metadata = {
        # KEDA requires the internal FQDN string to route through the environment mesh proxy
        host                  = azurerm_container_app.redis.ingress[0].fqdn
        port                  = "6379"
        listName              = "rq:queue:file-scanning"
        listLength            = "5"                      
        activationListLength  = "0"
        enableTLS             = "false"                  
        databaseIndex         = "0"
      }

      authentication {
        secret_name       = "redis-password"
        trigger_parameter = "password"
      }
    }
  }
}