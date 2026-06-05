#!/usr/bin/env bash
set -euo pipefail

# 项目依赖检查 / 安装 / 环境配置脚本
#
# 职责：
#   1. 检查系统级依赖（Node.js / npm、Python 3）
#   2. 配置 Python 虚拟环境（.venv）
#   3. 检查并安装项目级依赖（npm 包、Python 包）
#
# 用法：
#   ./scripts/setup.sh             # 仅检查依赖，缺失时提示安装方法
#   ./scripts/setup.sh --auto      # 检查依赖，可自动安装缺失工具

AUTO_INSTALL=false
if [[ "${1:-}" == "--auto" ]]; then
  AUTO_INSTALL=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== 项目环境配置 ==="
echo ""

MISSING_DEPS=()

# ==================================================================
# 1. 系统级依赖检查
# ==================================================================

# ---- 1.1 Node.js / npm ----
echo "[1/5] 检查 Node.js / npm..."
if command -v npm &>/dev/null; then
  NPM_VERSION=$(npm --version)
  echo "  ✓ npm 已安装 (v$NPM_VERSION)"
  HAS_NPM=true
else
  echo "  ✗ npm 未安装"
  HAS_NPM=false
  MISSING_DEPS+=("npm")

  echo ""
  echo "  安装方法："
  echo "    macOS:    brew install node"
  echo "    Ubuntu:   sudo apt install nodejs npm"
  echo "    通用:     https://nodejs.org/"
  echo "    nvm:      nvm install node"
fi

echo ""

# ---- 1.2 Python 3 ----
echo "[2/5] 检查 Python 3..."
if command -v python3 &>/dev/null; then
  PYTHON_VERSION=$(python3 --version 2>&1)
  echo "  ✓ $PYTHON_VERSION"
  HAS_PYTHON=true
else
  echo "  ✗ Python 3 未安装"
  HAS_PYTHON=false
  MISSING_DEPS+=("python3")

  echo ""
  echo "  安装方法："
  echo "    macOS:    brew install python"
  echo "    Ubuntu:   sudo apt install python3"
  echo "    pyenv:    pyenv install 3.12"
fi

echo ""

# ==================================================================
# 2. Python 虚拟环境配置
# ==================================================================

# ---- 2.1 检查 / 创建 .venv ----
echo "[3/5] 检查 Python 虚拟环境..."
VENV_DIR="$REPO_ROOT/.venv"

if [[ -d "$VENV_DIR" ]] && [[ -x "$VENV_DIR/bin/python3" ]]; then
  echo "  ✓ .venv 已存在"
  HAS_VENV=true
elif [[ "$HAS_PYTHON" == "true" ]]; then
  echo "  ⚠ .venv 不存在"

  if [[ "$AUTO_INSTALL" == "true" ]]; then
    echo "  → 正在创建虚拟环境..."
    cd "$REPO_ROOT"
    if python3 -m venv .venv; then
      echo "  ✓ 创建成功"
      HAS_VENV=true
    else
      echo "  ✗ 创建失败"
      HAS_VENV=false
    fi
  else
    echo "  创建方法："
    echo "    cd $REPO_ROOT && python3 -m venv .venv"
    HAS_VENV=false
    MISSING_DEPS+=("venv")
  fi
else
  echo "  ⚠ 需要先安装 Python 3"
  HAS_VENV=false
fi

echo ""

# ==================================================================
# 3. 项目级依赖安装
# ==================================================================

# ---- 3.1 markdownlint-cli2（项目级 npm 包）----
echo "[4/5] 检查 markdownlint-cli2..."

NODE_MODULES_BIN="$REPO_ROOT/node_modules/.bin/markdownlint-cli2"

if [[ -x "$NODE_MODULES_BIN" ]]; then
  MDLINT_VERSION=$("$NODE_MODULES_BIN" --version 2>/dev/null | head -1 || echo "unknown")
  echo "  ✓ markdownlint-cli2 已安装 (项目级, $MDLINT_VERSION)"
elif command -v markdownlint-cli2 &>/dev/null; then
  MDLINT_VERSION=$(markdownlint-cli2 --version 2>/dev/null | head -1 || echo "unknown")
  echo "  ✓ markdownlint-cli2 已安装 (全局, $MDLINT_VERSION)"
else
  echo "  ✗ markdownlint-cli2 未安装"
  MISSING_DEPS+=("markdownlint-cli2")

  if [[ "$HAS_NPM" == "true" ]]; then
    echo "  安装方法（项目级，推荐）："
    echo "    cd $REPO_ROOT && npm install --save-dev markdownlint-cli2@^0.15.0"
    echo ""
    echo "  或全局安装（需要 Node 20+）："
    echo "    npm install -g markdownlint-cli2"

    if [[ "$AUTO_INSTALL" == "true" ]]; then
      echo ""
      echo "  → 正在自动安装（项目级，兼容 Node 18）..."
      cd "$REPO_ROOT"
      if [[ ! -f "package.json" ]]; then
        echo '{"name": "yzr_ws", "version": "1.0.0", "private": true}' > package.json
      fi
      if npm install --save-dev markdownlint-cli2@^0.15.0; then
        echo "  ✓ 安装成功"
        MISSING_DEPS=("${MISSING_DEPS[@]/markdownlint-cli2}")
      else
        echo "  ✗ 安装失败，请手动安装"
      fi
    fi
  else
    echo "  ⚠ 需要先安装 npm 才能安装 markdownlint-cli2"
  fi
fi

echo ""

# ---- 3.2 ruff（项目级 Python 包，安装在 venv 中）----
echo "[5/5] 检查 ruff..."

VENV_RUFF="$VENV_DIR/bin/ruff"

if [[ -x "$VENV_RUFF" ]]; then
  RUFF_VERSION=$("$VENV_RUFF" version 2>/dev/null || echo "unknown")
  echo "  ✓ ruff 已安装 (venv, $RUFF_VERSION)"
elif command -v ruff &>/dev/null; then
  RUFF_VERSION=$(ruff version 2>/dev/null || echo "unknown")
  echo "  ✓ ruff 已安装 (全局, $RUFF_VERSION)"
  echo "  ⚠ 建议安装到 venv 以隔离环境"
else
  echo "  ✗ ruff 未安装"
  MISSING_DEPS+=("ruff")

  if [[ "$HAS_VENV" == "true" ]]; then
    echo "  安装方法（venv，推荐）："
    echo "    $VENV_DIR/bin/pip install ruff"
    echo ""
    echo "  或 pipx 全局安装："
    echo "    pipx install ruff"

    if [[ "$AUTO_INSTALL" == "true" ]]; then
      echo ""
      echo "  → 正在自动安装到 venv..."
      if "$VENV_DIR/bin/pip" install ruff; then
        echo "  ✓ 安装成功"
        MISSING_DEPS=("${MISSING_DEPS[@]/ruff}")
      else
        echo "  ✗ 安装失败，请手动安装"
      fi
    fi
  elif [[ "$HAS_PYTHON" == "true" ]]; then
    echo "  ⚠ 需要先创建 venv，或全局安装："
    echo "    pip install ruff"
  else
    echo "  ⚠ 需要先安装 Python 3 才能安装 ruff"
  fi
fi

echo ""

# ==================================================================
# 4. 汇总
# ==================================================================

FILTERED_MISSING=()
for dep in "${MISSING_DEPS[@]}"; do
  if [[ -n "$dep" ]]; then
    FILTERED_MISSING+=("$dep")
  fi
done

if [[ ${#FILTERED_MISSING[@]} -eq 0 ]]; then
  echo "=== 所有依赖已就绪 ==="
  echo ""
  echo "运行 lint 检查："
  echo "  ./scripts/lint.sh             # 全部 .md + .py 文件"
  echo "  ./scripts/lint.sh fix         # 自动修复"
  exit 0
else
  echo "=== 缺失依赖 ==="
  printf '  - %s\n' "${FILTERED_MISSING[@]}"
  echo ""
  if [[ "$AUTO_INSTALL" != "true" ]]; then
    echo "提示：运行 ./scripts/setup.sh --auto 可自动安装可安装的依赖"
  fi
  exit 1
fi
