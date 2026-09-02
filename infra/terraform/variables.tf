variable "project_name" {
  description = "Lowercase name used to prefix AWS resources."
  type        = string
  default     = "catalogops"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-22 lowercase letters, digits, or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be dev, staging, or production."
  }
}

variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "ap-southeast-1"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the isolated CatalogOps VPC."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "allowed_ipv4_cidrs" {
  description = "IPv4 ranges allowed to reach the public load balancer."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "certificate_arn" {
  description = "ACM certificate ARN in aws_region for HTTPS on the application load balancer."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    error_message = "certificate_arn must be an ACM certificate ARN."
  }
}

variable "hosted_zone_id" {
  description = "Route 53 public hosted zone ID used for the application alias."
  type        = string
}

variable "application_hostname" {
  description = "Public hostname covered by certificate_arn, for example catalogops.example.com."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", var.application_hostname))
    error_message = "application_hostname must be a fully qualified DNS hostname."
  }
}

variable "api_image" {
  description = "Immutable API container image URI, preferably pinned by digest or commit SHA."
  type        = string
}

variable "web_image" {
  description = "Immutable web container image URI, preferably pinned by digest or commit SHA."
  type        = string
}

variable "api_desired_count" {
  description = "Steady-state API task count. Use at least two for production availability."
  type        = number
  default     = 1

  validation {
    condition     = var.api_desired_count >= 1
    error_message = "api_desired_count must be at least one."
  }
}

variable "web_desired_count" {
  description = "Steady-state web task count. Use at least two for production availability."
  type        = number
  default     = 1

  validation {
    condition     = var.web_desired_count >= 1
    error_message = "web_desired_count must be at least one."
  }
}

variable "api_cpu" {
  description = "Fargate CPU units allocated to each API task."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate memory in MiB allocated to each API task."
  type        = number
  default     = 1024
}

variable "web_cpu" {
  description = "Fargate CPU units allocated to each web task."
  type        = number
  default     = 256
}

variable "web_memory" {
  description = "Fargate memory in MiB allocated to each web task."
  type        = number
  default     = 512
}

variable "db_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "catalogops"
}

variable "db_username" {
  description = "PostgreSQL master username; its generated password is stored in Secrets Manager."
  type        = string
  default     = "catalogopsadmin"
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS PostgreSQL instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial RDS gp3 storage in GiB."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum RDS storage autoscaling limit in GiB."
  type        = number
  default     = 100
}

variable "db_multi_az" {
  description = "Run RDS with a synchronous standby in another availability zone."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Protect the ALB and RDS database from accidental deletion."
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "Skip the final RDS snapshot on destroy. Keep false outside disposable development."
  type        = bool
  default     = false
}

variable "artifact_force_destroy" {
  description = "Allow Terraform to delete a non-empty artifact bucket. Keep false for shared environments."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention period."
  type        = number
  default     = 30
}

variable "alarm_topic_arn" {
  description = "Optional SNS topic ARN for CloudWatch alarm actions."
  type        = string
  default     = null
  nullable    = true
}
