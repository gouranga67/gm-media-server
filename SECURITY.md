# Security policy

## Supported versions

GM Studio is pre-1.0 software. Security fixes are applied to the latest commit on the default branch.

## Reporting a vulnerability

Do not open a public issue containing credentials, private media, tailnet details, or a working exploit. Until a private reporting address is published, use GitHub's private vulnerability reporting feature for this repository.

Include the affected component, reproduction conditions, likely impact, and a minimal proof of concept that contains no real footage or credentials. Maintainers will acknowledge a report when capacity allows; this community project does not promise a response time.

## Deployment warning

The current application is designed for a trusted, private tailnet. It does not yet provide complete public-internet authentication or multi-tenant isolation. Do not expose its web port with Tailscale Funnel, a public reverse proxy, router port forwarding, or a public cloud load balancer.

Keep `.env`, ChatGPT OAuth records, database backups, media volumes, logs, and provenance manifests outside source control. If an OAuth credential may have leaked, disconnect the app in ChatGPT settings and rotate any other affected secrets.
