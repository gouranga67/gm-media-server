#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )) || [[ "$2" != "--confirm-commercial-use" ]]; then
  printf 'Usage: sudo %s /absolute/path/to/download-directory --confirm-commercial-use\n' "$0" >&2
  printf 'The confirmation records that you reviewed the Pixabay licence for these downloads.\n' >&2
  exit 2
fi

source_directory=$1
if [[ "$source_directory" != /* || ! -d "$source_directory" ]]; then
  printf 'The source directory must be an existing absolute path.\n' >&2
  exit 2
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
proof='User-supplied Pixabay download; individual source page and Pixabay Content License recorded by the GM Studio operator.'

import_track() {
  local filename=$1
  shift
  local source_path="$source_directory/$filename"
  if [[ ! -f "$source_path" ]]; then
    printf 'Missing required track: %s\n' "$source_path" >&2
    exit 2
  fi
  "$project_root/scripts/import-music.sh" "$source_path" \
    "$@" \
    --license-name 'Pixabay Content License' \
    --license-proof "$proof" \
    --platform all_social \
    --commercial-use-confirmed
}

import_track 'danyvin-chill-rnb-621264.mp3' \
  --title 'Chill RnB' \
  --artist 'danyvin' \
  --mood 'chill relaxed' \
  --energy low \
  --license-source-url 'https://pixabay.com/music/rnb-chill-rnb-621264/' \
  --attribution 'danyvin via Pixabay'

import_track 'kornevmusic-happy-latin-salsa-dance-621026.mp3' \
  --title 'Happy Latin Salsa Dance' \
  --artist 'kornevmusic' \
  --mood 'happy latin dance' \
  --energy high \
  --license-source-url 'https://pixabay.com/music/salsa-happy-latin-salsa-dance-621026/' \
  --attribution 'kornevmusic via Pixabay'

import_track 'loka_music-inspiring-travel-acoustic-621191.mp3' \
  --title 'Inspiring Travel Acoustic' \
  --artist 'Loka_music' \
  --mood 'uplifting acoustic travel' \
  --energy medium \
  --license-source-url 'https://pixabay.com/music/folk-inspiring-travel-acoustic-621191/' \
  --attribution 'Loka_music via Pixabay'

import_track 'miromaxmusic-stylish-funk-smooth-party-no-copyright-620664.mp3' \
  --title 'Stylish Funk Smooth Party No Copyright' \
  --artist 'MiroMaxMusic' \
  --mood 'groovy upbeat funk' \
  --energy high \
  --license-source-url 'https://pixabay.com/music/funk-stylish-funk-smooth-party-no-copyright-620664/' \
  --attribution 'MiroMaxMusic via Pixabay'

printf 'Imported the GM Studio Pixabay starter music library.\n'
