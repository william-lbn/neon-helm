set -eu
export KUBECONFIG=${KUBECONFIG:?Explicit kubeconfig required}
python3 -B "$(dirname "$0")/verify-lifecycle.py" "$@"
