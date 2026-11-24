#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 4 || "$4" != --erase-data ]]; then
  echo '用法: standard-clean.sh SITE_JSON PRIVATE_STATE EXACT_SITE_NAME --erase-data' >&2
  exit 2
fi
entry=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
checker=${NEON_HOST_CHECK:-"$entry/../bin/host-decommission-check"}
for action in plan stop-host-writers end-host-domains handoff-ordinary cleanup-host-artifacts uninstall erase-data verify-empty; do
  python3 -B "$entry/standard-uninstall.py" "$action" --site "$1" --state "$2" --confirm-site "$3" --host-check "$checker" --erase-data
done
