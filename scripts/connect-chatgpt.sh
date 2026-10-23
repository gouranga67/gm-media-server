#!/usr/bin/env bash
set -euo pipefail

cat <<'MESSAGE'
OpenAI's self-hosted-VM procedure completes OAuth on the computer running the
browser, then transfers the protected credential to this server.

On that computer:
  1. Copy scripts/chatgpt-enroll-local.py from this repository.
  2. Install its one dependency: py -m pip install "PyJWT[crypto]==2.10.1"
  3. Run: py chatgpt-enroll-local.py
  4. Securely copy gm-studio-chatgpt.json to:
       /tmp/gm-studio-chatgpt.json

Then, on this server, run:
  sudo ./scripts/import-chatgpt.sh
MESSAGE
