terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# No backend is configured yet: HCP organisation/workspace must be chosen first.
# Do not plan against production or apply until the resources are safely adopted.
provider "aws" {
  region = "eu-north-1"
}
