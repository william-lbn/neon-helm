#!/usr/bin/env bash
# Run on each Linux node before admitting a build, pull, or Compute E2E suite.
# Read-only admission check: never tunes fsync, caches, or services.
set -euo pipefail
export LC_ALL=C
io_max=${NEON_PREFLIGHT_IO_SOME_MAX:-5}
memory_min=${NEON_PREFLIGHT_MEMORY_AVAILABLE_MIB:-4096}
[[ "$io_max" =~ ^(0|[1-9][0-9]*)([.][0-9]+)?$ && "$memory_min" =~ ^(0|[1-9][0-9]*)$ ]] || {
  echo 'Invalid pressure threshold' >&2; exit 2;
}
io_some=$(awk '$1=="some" {split($2,a,"=");print a[2]}' /proc/pressure/io)
io_full=$(awk '$1=="full" {split($2,a,"=");print a[2]}' /proc/pressure/io)
memory_some=$(awk '$1=="some" {split($2,a,"=");print a[2]}' /proc/pressure/memory)
available=$(awk '$1=="MemAvailable:" {printf "%d",$2/1024}' /proc/meminfo)
[[ -n "$io_some" && -n "$io_full" && -n "$memory_some" && -n "$available" ]] || {
  echo 'Required Linux pressure/memory metrics unavailable' >&2; exit 2;
}
state=pass
if ! awk -v io="$io_some" -v max="$io_max" -v mem="$memory_some" \
  -v available="$available" -v min="$memory_min" \
  'BEGIN {exit !(io<=max && mem<=0.10 && available>=min)}'; then state=fail; fi
printf '{"result":"%s","io_some_avg10":%s,"io_full_avg10":%s,"memory_some_avg10":%s,"memory_available_mib":%s,"io_limit":%s,"memory_min_mib":%s}\n' \
  "$state" "$io_some" "$io_full" "$memory_some" "$available" "$io_max" "$memory_min"
[[ "$state" == pass ]]
