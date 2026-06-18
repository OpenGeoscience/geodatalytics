variable "SENTRY_AUTH_TOKEN" {
  type      = string
  nullable  = false
  sensitive = true
}

variable "DJANGO_UVDAT_HF_TOKEN" {
  type      = string
  nullable  = true
  sensitive = true
}
