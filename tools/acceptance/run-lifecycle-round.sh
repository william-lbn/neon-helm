set -eu
pg=${1:?}; caseID=${2:?}; mode=${3:?suspend or retry-suspend}
case "$mode" in suspend|retry-suspend) ;; *) exit 2;; esac
entry=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bash "$entry/verify-lifecycle.sh" "$pg" "$caseID" "$mode"
bash "$entry/verify-lifecycle.sh" "$pg" "$caseID" resume
bash "$entry/verify-lifecycle.sh" "$pg" "$caseID" verify
