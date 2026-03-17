locals {
  www_env_vars = {
    VITE_APP_API_ROOT = "https://${module.django.fqdn}/"
  }
}

data "cloudflare_accounts" "this" {
  name = "Kitware"
}

resource "cloudflare_pages_project" "www" {
  account_id        = data.cloudflare_accounts.this.accounts[0].id
  name              = "geodatalytics"
  production_branch = "master"

  source {
    type = "github"
    config {
      production_branch = "master"
      owner             = "OpenGeoscience"
      repo_name         = "geodatalytics"
    }
  }

  build_config {
    build_caching   = true
    root_dir        = "web"
    build_command   = "npm run build"
    destination_dir = "dist"
  }

  deployment_configs {
    preview {
      environment_variables = local.www_env_vars
    }
    production {
      environment_variables = merge(
        local.www_env_vars,
        {
          VITE_APP_SENTRY_DSN = ""
          # SENTRY_AUTH_TOKEN is also set manually in the Cloudflare Pages console,
          # but it's a secret, so don't include it here.
        },
      )
    }
  }
}

resource "cloudflare_pages_domain" "www" {
  account_id   = data.cloudflare_accounts.this.accounts[0].id
  project_name = cloudflare_pages_project.www.name
  domain       = aws_route53_record.www.fqdn
}

resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.this.zone_id
  name    = "www"
  type    = "CNAME"
  ttl     = 300
  records = [cloudflare_pages_project.www.subdomain]
}
