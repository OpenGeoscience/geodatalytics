# Redirect requests for the apex domain to the Django subdomain ("www.")

resource "aws_s3_bucket" "apex_redirect" {
  bucket = aws_route53_zone.this.name
}

resource "aws_s3_bucket_website_configuration" "apex_redirect" {
  bucket = aws_s3_bucket.apex_redirect.id

  redirect_all_requests_to {
    host_name = module.django.fqdn
    protocol  = "https"
  }
}

resource "aws_route53_record" "apex_redirect" {
  zone_id = aws_route53_zone.this.zone_id
  name    = aws_route53_zone.this.name
  type    = "A"

  alias {
    name                   = aws_s3_bucket_website_configuration.apex_redirect.website_domain
    zone_id                = aws_s3_bucket.apex_redirect.hosted_zone_id
    evaluate_target_health = false
  }
}
