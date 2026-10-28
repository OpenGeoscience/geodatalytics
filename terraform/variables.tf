variable "SENTRY_AUTH_TOKEN" {
  type      = string
  nullable  = false
  sensitive = true
}

variable "DJANGO_UVDAT_DEEPINFRA_TOKEN" {
  type      = string
  nullable  = true
  sensitive = true
}
