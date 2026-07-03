locals {
  www_env_vars = {
    VITE_API_ROOT = "https://${module.django.fqdn}/"
  }
}

data "cloudflare_account" "this" {
  # Kitware
  account_id = "b7ba799b50a979650d3362e965257042"
}

resource "cloudflare_pages_project" "www" {
  account_id        = data.cloudflare_account.this.id
  name              = "geodatalytics"
  production_branch = "master"

  source = {
    type = "github"
    config = {
      production_branch = "master"
      owner             = "OpenGeoscience"
      repo_name         = "geodatalytics"
      path_includes     = ["web/*"]
    }
  }

  build_config = {
    build_caching   = true
    root_dir        = "web"
    build_command   = "npm run build"
    destination_dir = "dist"
  }

  deployment_configs = {
    preview = {
      env_vars = {
        for k, v in local.www_env_vars : k => {
          type  = "plain_text"
          value = v
        }
      }
    }
    production = {
      env_vars = merge(
        {
          for k, v in local.www_env_vars : k => {
            type  = "plain_text"
            value = v
          }
        },
        {
          VITE_SENTRY_DSN = {
            type  = "plain_text"
            value = "https://648b9234b2fc2df0dd59192ddb0111f7@o267860.ingest.us.sentry.io/4511108704501760"
          }
          SENTRY_AUTH_TOKEN = {
            type  = "secret_text"
            value = var.SENTRY_AUTH_TOKEN
          }
        },
      )
    }
  }
}

resource "cloudflare_pages_domain" "www" {
  account_id   = data.cloudflare_account.this.id
  project_name = cloudflare_pages_project.www.name
  name         = aws_route53_record.www.fqdn
}

resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.this.zone_id
  name    = "www"
  type    = "CNAME"
  ttl     = 300
  records = [cloudflare_pages_project.www.subdomain]
}
