# =============================================================================
# dependencies.tf
# =============================================================================
# Declares resources worker_scale_rule.tf references but doesn't define itself:
# the storage account lookup and the generated Redis password.

# -----------------------------------------------------------------------
# Storage account name/resource group — PLACEHOLDER, pre-filled with the
# real values from your Azure portal setup (stguardrailscans / rg-guardrail).
# Override these if the storage account is ever recreated under a
# different name or moved to a different resource group.
# -----------------------------------------------------------------------
variable "storage_account_name" {
  description = "Name of the pre-provisioned Azure Storage account (created manually in the portal, not by Terraform)"
  type        = string
  default     = "stguardrailscans"  # <-- placeholder, confirm this matches your portal setup
}

variable "storage_resource_group_name" {
  description = "Resource group containing the storage account"
  type        = string
  default     = "rg-guardrail"  # <-- placeholder, confirm this matches your portal setup
}

# This is a data source, not a resource — Terraform reads the existing
# storage account's properties without trying to create or modify it,
# since you provisioned it by hand in the portal.
data "azurerm_storage_account" "guardrail" {
  name                = var.storage_account_name
  resource_group_name = var.storage_resource_group_name
}

# -----------------------------------------------------------------------
# Redis password — generated once by Terraform, stored in state, reused
# everywhere else that needs it (the Redis container's own --requirepass
# flag, and the worker/API's REDIS_URL connection string).
# -----------------------------------------------------------------------
resource "random_password" "redis" {
  length  = 32
  special = false  # avoid characters that need escaping in connection strings / KEDA scaler metadata
}