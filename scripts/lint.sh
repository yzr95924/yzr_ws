#!/usr/bin/env bash
set -euo pipefail

# Lint 统一入口：对仓库内全部 .md 和 .py 文件执行 lint 检查
#
# 用法：
#   ./scripts/lint.sh             # 检查全部 .md + .py 文件
#   ./scripts/lint.sh fix         # 自动修复可修复的问题

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/python/lint_md.py" "$@"
python3 "$SCRIPT_DIR/python/lint_py.py" "$@"
