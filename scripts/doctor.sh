#!/usr/bin/env bash
set -u

pass=0
warn=0
fail=0
host_inspection_restricted=0

ok() {
  pass=$((pass + 1))
  printf 'PASS  %s\n' "$1"
}

warning() {
  warn=$((warn + 1))
  printf 'WARN  %s\n' "$1"
}

failure() {
  fail=$((fail + 1))
  printf 'FAIL  %s\n' "$1"
}

command_version() {
  local label="$1"
  shift
  if output=$("$@" 2>&1); then
    ok "$label: ${output%%$'\n'*}"
  else
    failure "$label is unavailable"
  fi
}

printf 'GM Media Server doctor (read-only)\n\n'

command_version "Docker CLI" docker --version
command_version "Docker Compose" docker compose version
command_version "Node" node --version
command_version "npm" npm --version
command_version "Tailscale" tailscale version

node_major=$(node --version 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || true)
if [[ "$node_major" == "24" ]]; then
  ok "Node major version matches the project pin (24)"
else
  warning "Node 24 is required; active host runtime is ${node_major:-unknown}"
fi

check_system_service() {
  local unit="$1"
  local label="$2"
  local output
  if output=$(systemctl is-active "$unit" 2>&1); then
    ok "$label service is active"
  elif [[ "$output" == "inactive" || "$output" == "failed" ]]; then
    failure "$label service is $output"
  else
    host_inspection_restricted=1
    warning "$label service state is unavailable from this execution context"
  fi
}

check_system_service docker Docker
check_system_service tailscaled Tailscale

if nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
  gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)
  ok "NVIDIA GPU visible on host: $gpu_name"
else
  if (( host_inspection_restricted > 0 )); then
    warning "NVIDIA GPU state is unavailable from this execution context"
  elif compgen -G '/dev/nvidia*' >/dev/null; then
    failure "NVIDIA device exists but nvidia-smi cannot communicate with it"
  else
    warning "NVIDIA devices are unavailable from this execution context"
  fi
fi

if docker info >/dev/null 2>&1; then
  ok "Current user can access the Docker daemon"
else
  warning "Current user cannot access the Docker daemon; deployment requires a root-managed path"
fi

if [[ -f package-lock.json && -d node_modules ]]; then
  ok "Node dependency lock and install directory are present"
else
  warning "Node dependencies are not fully installed"
fi

if [[ -f .env ]]; then
  ok "Local .env exists"
else
  warning "Local .env is not configured yet (expected before Phase 2 startup)"
fi

printf '\nSummary: %d passed, %d warnings, %d failed\n' "$pass" "$warn" "$fail"

if (( fail > 0 )); then
  exit 1
fi
