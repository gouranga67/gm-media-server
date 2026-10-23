# Open-source release checklist

This checklist separates publishing the software from operating a private GM Studio appliance. Publishing source code never requires publishing a deployment's media, data, network identity, or credentials.

## Before every public release

1. Run `./scripts/check-public-release.sh` and resolve every finding.
2. Run the TypeScript, production web build, Python compilation, and Compose configuration checks documented in the README.
3. Review `git diff --cached` and the complete candidate file list, including newly added files.
4. Confirm `.env`, OAuth transfer files, private keys, media, databases, logs, generated previews, and machine-specific paths are absent.
5. Confirm examples contain only placeholder hostnames and identities.
6. Confirm the security warning still matches the deployed authentication boundary.
7. Publish a source tag or release notes that identify the exact commit tested.

## Private deployment data

The following belong only on the appliance or its encrypted backup:

- `.env` and provider secrets
- the `auth-data`, database, Redis, and upload volumes
- originals, proxies, transcripts, thumbnails, previews, exports, and manifests
- Tailscale machine names, tailnet DNS names, IP addresses, and access policy
- service journals or logs that can contain job and asset identifiers

Do not use real private data as public fixtures. Generate synthetic metadata and tiny purpose-made test signals that contain no personal content.

## ChatGPT plan sharing

This repository uses the open-source/self-hosted Sign in with ChatGPT flow. A maintainer must keep the integration aligned with OpenAI's token-sharing requirements, including local browser authorization, VM-bound credential storage, `store: false`, streaming responses, and clear in-product plan-usage disclosure.

Never commit the one-time `gm-studio-chatgpt.json` transfer file or the VM's stored credential. Users must authorize their own installations; a maintainer credential must not be bundled or shared.

## Publishing boundary

The public repository should contain source code, migrations, documentation, safe templates, and tests. A public Git host is not the deployment target. The running application should remain reachable only through the operator's private tailnet until the hardening phase explicitly adds and verifies a public authentication model.
