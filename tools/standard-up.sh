#!/usr/bin/env bash
# 一次入口只创建全新操作；失败时保留原目录并按原收据观察，不能重放未知安装。
set -euo pipefail
if [[ $# != 2 ]]; then
  echo '用法：standard-up.sh SITE_INPUT_JSON NEW_PRIVATE_OPERATION_DIRECTORY' >&2
  exit 2
fi
entry=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$entry/../bin:$PATH"
umask 077
if ! mkdir -m 700 -- "$2"; then
  echo '操作目录已存在或不可创建；请检查原收据，不能覆盖或从头重放。' >&2
  exit 1
fi
python3 -B "$entry/standard-init.py" --config "$1" --out "$2/config"
python3 -B "$entry/standard-site.py" install --site "$2/config/site.json" --state "$2/install"
