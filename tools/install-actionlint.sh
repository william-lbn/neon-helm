#!/usr/bin/env bash
set -euo pipefail
task_dir="${1:?Destination directory required}"
task_version="$(node -p "require('./locks/tools.json').actionlint.version")"
task_sha="$(node -p "require('./locks/tools.json').actionlint.linux_amd64_sha256")"
mkdir -p "$task_dir"
task_archive="$task_dir/actionlint.tar.gz"
curl --fail --location --retry 2 --proto '=https' --tlsv1.2 \
  "https://github.com/rhysd/actionlint/releases/download/v$task_version/actionlint_${task_version}_linux_amd64.tar.gz" -o "$task_archive"
printf '%s  %s\n' "$task_sha" "$task_archive" | sha256sum --check --status
tar -xzf "$task_archive" -C "$task_dir" actionlint
