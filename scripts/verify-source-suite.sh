#!/usr/bin/env bash
set -u

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

passed=0
failed=0

run_check() {
  local label=$1
  shift
  printf '\n== %s ==\n' "$label"
  if "$@"; then
    passed=$((passed + 1))
    printf 'PASS  %s\n' "$label"
  else
    failed=$((failed + 1))
    printf 'FAIL  %s\n' "$label" >&2
  fi
}

run_check "Compose configuration" docker compose config --quiet
run_check "Python source compilation" python3 -m compileall -q services/core/app services/core/tests scripts
run_check "Public-release secret and media audit" npm run audit:public
run_check "Web TypeScript" npm run typecheck:web
run_check "Media library, concepts, and upload interactions" npm run test:media-selection
run_check "Agent tool TypeScript" \
  npx tsc --noEmit --module esnext --moduleResolution bundler --target es2022 --skipLibCheck \
  agent/tools/search_library.ts agent/tools/attach_library_assets.ts \
  agent/tools/submit_edit_plan.ts agent/tools/apply_finishing.ts \
  agent/tools/apply_precise_edit.ts agent/tools/inspect_edit_tools.ts
run_check "Production web build" npm run build:web
run_check "Whitespace and patch integrity" git diff --check

printf '\nSource-suite summary: %d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
