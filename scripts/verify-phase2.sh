#!/usr/bin/env bash
set -u

pass=0
fail=0

ok() {
  pass=$((pass + 1))
  printf 'PASS  %s\n' "$1"
}

failure() {
  fail=$((fail + 1))
  printf 'FAIL  %s\n' "$1"
}

if docker compose config --quiet; then
  ok "Compose configuration is valid"
else
  failure "Compose configuration is invalid"
fi

if [[ -f apps/web/.next/standalone/apps/web/server.js ]]; then
  ok "Standalone web server artifact exists"
else
  failure "Standalone web server artifact is missing; run npm run build:web with Node 24"
fi

if python3 - <<'PY'
import ast
from pathlib import Path
for source in Path("services/core/app").glob("*.py"):
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
PY
then
  ok "Python service sources parse"
else
  failure "Python service source parsing failed"
fi

if docker info >/dev/null 2>&1; then
  if docker compose ps --status running --format json | grep -q 'gm-media-server'; then
    ok "At least one project container is running"
  else
    failure "Docker is accessible but the project stack is not running"
  fi
else
  printf 'SKIP  Live container checks require root-managed Docker access\n'
fi

printf '\nSummary: %d passed, %d failed\n' "$pass" "$fail"
(( fail == 0 ))
