data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  name = "${var.project_name}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  tags = {
    Application = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Repository  = "CatalogOps"
  }
}

