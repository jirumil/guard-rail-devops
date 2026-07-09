terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.116"
    }
  }

  # Local state is fine for a portfolio project. If you want to show you
  # understand remote state for a team setting, mention it in your README
  # and optionally add an azurerm backend block pointing at a Storage Account.
}

provider "azurerm" {
  features {}
  skip_provider_registration = true
}
