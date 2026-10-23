#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 )); then
  printf 'Usage: %s /absolute/path/to/track.mp3 [music import options]\n' "$0" >&2
  printf 'Run with --help after the path to list required licence metadata.\n' >&2
  exit 2
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_path=$1
shift

source_name=$(basename "$source_path")
source_extension=${source_name##*.}
if [[ "$source_name" == "$source_extension" ]]; then
  printf 'The music source must have a supported file extension.\n' >&2
  exit 2
fi
container_source="/import/track.${source_extension,,}"

if [[ "$source_path" != /* || ! -f "$source_path" ]]; then
  printf 'The music source must be an existing absolute file path.\n' >&2
  exit 2
fi

cd "$project_root"
exec docker compose run --rm --no-deps \
  --volume "$source_path:$container_source:ro" \
  worker python -m app.music_import --source "$container_source" "$@"
