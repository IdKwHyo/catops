output "application_url" {
  description = "Public HTTPS endpoint."
  value       = "https://${var.application_hostname}"
}

output "load_balancer_dns_name" {
  description = "ALB DNS name for a Route 53 alias or external DNS CNAME."
  value       = aws_lb.main.dns_name
}

output "api_ecr_repository_url" {
  description = "ECR repository for immutable API images."
  value       = aws_ecr_repository.api.repository_url
}

output "web_ecr_repository_url" {
  description = "ECR repository for immutable web images."
  value       = aws_ecr_repository.web.repository_url
}

output "artifact_bucket" {
  description = "Private, encrypted, versioned model artifact bucket."
  value       = aws_s3_bucket.artifacts.id
}

output "audit_bucket" {
  description = "Private audit evidence bucket with 30-day governance retention."
  value       = aws_s3_bucket.audit.id
}

output "database_endpoint" {
  description = "Private RDS endpoint; reachable only by API tasks in the VPC."
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "database_secret_arn" {
  description = "Secrets Manager ARN containing the generated RDS credentials."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
  sensitive   = true
}

output "ecs_cluster_name" {
  description = "ECS cluster used by deployment automation."
  value       = aws_ecs_cluster.main.name
}

output "cloudwatch_dashboard" {
  description = "Operational CloudWatch dashboard name."
  value       = aws_cloudwatch_dashboard.operations.dashboard_name
}
