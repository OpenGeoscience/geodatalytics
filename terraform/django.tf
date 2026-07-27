resource "aws_route53_zone" "this" {
  name = "geodatalytics.kitware.com"
}

data "heroku_team" "this" {
  name = "kitware"
}

module "django" {
  source  = "kitware-resonant/resonant/heroku"
  version = "3.3.0"

  project_slug           = "geodatalytics"
  route53_zone_id        = aws_route53_zone.this.zone_id
  heroku_team_name       = data.heroku_team.this.name
  subdomain_name         = "api"
  django_settings_module = "uvdat.settings.heroku_production"

  ec2_worker_instance_quantity = 1
  ec2_worker_ssh_public_key    = file("${path.module}/ssh-key.pub")

  additional_django_vars = {
    DJANGO_UVDAT_WEB_URL           = "https://www.geodatalytics.kitware.com/"
    DJANGO_DATABASE_POOL_MAX_SIZE  = "12"
    DJANGO_SENTRY_DSN              = "https://5302701c88f1fa6ec056e0c269071191@o267860.ingest.us.sentry.io/4510620385804288"
    DJANGO_UVDAT_HF_NAMESPACE      = "Kitware"
    DJANGO_UVDAT_HF_ENDPOINT_NAMES = "qwen=qwen3-5-9b-gguf-ulh,"
  }
  additional_sensitive_django_vars = {
    DJANGO_UVDAT_HF_TOKEN = var.DJANGO_UVDAT_HF_TOKEN
  }
  django_cors_allowed_origins = [
    # Can't make this use "aws_route53_record.www.fqdn" because of a circular dependency
    "https://www.geodatalytics.kitware.com",
  ]
  django_cors_allowed_origin_regexes = [
    # Can't base this on "cloudflare_pages_project.www.subdomain" because of a circular dependency
    "https://[\\w-]+\\.geodatalytics\\.pages\\.dev",
  ]

  # Disable workers; they require "tasks" dependencies, which are too large for Heroku to install
  heroku_worker_dyno_quantity = 0
}

resource "heroku_addon" "redis" {
  app_id = module.django.heroku_app_id
  plan   = "heroku-redis:mini"

  config = {
    maxmemory_policy = "volatile-lru"
  }
}

output "dns_nameservers" {
  value = aws_route53_zone.this.name_servers
}

output "ec2_worker_hostnames" {
  value = module.django.ec2_worker_hostnames
}
