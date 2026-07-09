variable "project" {
  description = "Short project name used as a prefix for resource names"
  type        = string
  default     = "guardrail"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Deployment environment tag"
  type        = string
  default     = "dev"
}

variable "container_registry_name" {
  description = "Globally unique ACR name (alphanumeric only)"
  type        = string
  default     = "guardrailcr"
}

variable "api_image_tag" {
  description = "Immutable tag of the api image to deploy — a git SHA, never a default. Required, no fallback, so a forgotten -var fails loudly instead of silently redeploying stale bits."
  type        = string

  validation {
    condition     = var.api_image_tag != "latest" && var.api_image_tag != ""
    error_message = "api_image_tag must be an explicit, immutable tag (e.g. a git SHA) — \"latest\" is banned because Terraform can't detect a diff in a tag string that never changes, so Azure Container Apps would never re-pull."
  }
}

variable "worker_image_tag" {
  description = "Immutable tag of the worker image to deploy — a git SHA, never a default."
  type        = string

  validation {
    condition     = var.worker_image_tag != "latest" && var.worker_image_tag != ""
    error_message = "worker_image_tag must be an explicit, immutable tag (e.g. a git SHA) — \"latest\" is banned. See api_image_tag's validation message for why."
  }
}

variable "frontend_image_tag" {
  description = "Immutable tag of the frontend image to deploy — a git SHA, never a default."
  type        = string

  validation {
    condition     = var.frontend_image_tag != "latest" && var.frontend_image_tag != ""
    error_message = "frontend_image_tag must be an explicit, immutable tag (e.g. a git SHA) — \"latest\" is banned. See api_image_tag's validation message for why."
  }
}
