resource "aws_route53_record" "application" {
  zone_id = var.hosted_zone_id
  name    = var.application_hostname
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

