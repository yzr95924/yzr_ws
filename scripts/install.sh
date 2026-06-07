#!/usr/bin/env bash
# install.sh — 安装 yzrws 到本地 PATH，并按需安装 shell 补全
#
# 职责：
#   1. 把仓库内 bin/yzrws 软链接到 <prefix>/bin/yzrws（默认 ~/.local/bin），
#      使 yzrws 可在任意目录下直接调用
#   2. 调用 install-completions.sh 把 bash/zsh/fish 补全安装到标准目录
#
# 与 install-completions.sh 的关系：补全安装的具体路径与 shell 推断逻辑
# 全部复用 install-completions.sh，本脚本只负责 yzrws 主入口 + 转发参数。
#
# 用法：
#   ./scripts/install.sh                          # 安装到 ~/.local/bin，按 $SHELL 装补全
#   ./scripts/install.sh --prefix /opt/yzrws      # 整体安装到 /opt/yzrws（需写入权限）
#   ./scripts/install.sh --bin-dir ~/.local/bin   # 仅指定 bin 目录
#   ./scripts/install.sh --shell all              # 为所有 shell 装补全
#   ./scripts/install.sh --shell bash             # 显式指定 shell
#   ./scripts/install.sh --shell none             # 只装主命令，不动补全
#   ./scripts/install.sh --no-completions         # 同 --shell none
#   ./scripts/install.sh --dest-base /tmp/staging  # 测试场景：补全装到 /tmp/staging/.local/...
#                                                 # （默认 $HOME，透传给 install-completions.sh）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_BIN="$REPO_ROOT/bin/yzrws"
COMPLETIONS_SCRIPT="$SCRIPT_DIR/install-completions.sh"

# 解析参数
PREFIX="$HOME/.local"
BIN_DIR=""
SHELL_TARGET=""
NO_COMPLETIONS=false
DEST_BASE="$HOME"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="${2:-}"
            shift 2
            ;;
        --bin-dir)
            BIN_DIR="${2:-}"
            shift 2
            ;;
        --shell)
            SHELL_TARGET="${2:-}"
            shift 2
            ;;
        --no-completions)
            NO_COMPLETIONS=true
            shift
            ;;
        --dest-base)
            DEST_BASE="${2:-}"
            shift 2
            ;;
        -h|--help)
            sed -n '2,21p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 2
            ;;
    esac
done

# 校验关键参数
if [[ -z "$PREFIX" ]]; then
    echo "错误：--prefix 不能为空" >&2
    exit 2
fi
if [[ -z "$DEST_BASE" ]]; then
    echo "错误：--dest-base 不能为空" >&2
    exit 2
fi
if [[ ! -f "$SOURCE_BIN" ]]; then
    echo "错误：缺少 $SOURCE_BIN" >&2
    exit 1
fi
if [[ ! -x "$SOURCE_BIN" ]]; then
    echo "错误：$SOURCE_BIN 不可执行，请检查仓库文件" >&2
    exit 1
fi
if [[ ! -f "$COMPLETIONS_SCRIPT" ]]; then
    echo "错误：缺少 $COMPLETIONS_SCRIPT" >&2
    exit 1
fi

# 由 --prefix 推导默认 --bin-dir
if [[ -z "$BIN_DIR" ]]; then
    BIN_DIR="$PREFIX/bin"
fi
if [[ -z "$BIN_DIR" ]]; then
    echo "错误：无法确定 bin 目录" >&2
    exit 2
fi

# 推断默认 shell（仅在用户既未指定 --shell 也未传 --no-completions 时使用）
if [[ "$NO_COMPLETIONS" == "false" && -z "$SHELL_TARGET" ]]; then
    SHELL_TARGET=$(basename "${SHELL:-/bin/bash}")
fi

# ==================================================================
# 1. 安装主命令：创建 <bin_dir>/yzrws 软链接
# ==================================================================

DEST_BIN="$BIN_DIR/yzrws"

echo "=== yzrws 安装 ==="
echo ""
echo "[1/2] 链接主命令..."
echo "  src: $SOURCE_BIN"
echo "  dst: $DEST_BIN"

mkdir -p "$BIN_DIR"

# 已存在的情况：若指向同一源文件则视为已是最新，跳过；否则报错避免覆盖。
if [[ -e "$DEST_BIN" || -L "$DEST_BIN" ]]; then
    if [[ -L "$DEST_BIN" ]]; then
        current_target=$(readlink "$DEST_BIN")
        if [[ "$current_target" == "$SOURCE_BIN" ]]; then
            echo "  ✓ 软链接已存在且指向正确源文件，跳过"
        else
            echo "  错误：$DEST_BIN 已存在且指向其他位置：$current_target" >&2
            echo "  请先手动移除或运行 ./scripts/uninstall.sh" >&2
            exit 1
        fi
    else
        echo "  错误：$DEST_BIN 已存在且不是符号链接" >&2
        echo "  请先手动移除或运行 ./scripts/uninstall.sh" >&2
        exit 1
    fi
else
    ln -s "$SOURCE_BIN" "$DEST_BIN"
    echo "  ✓ 已创建软链接"
fi

# ==================================================================
# 2. 安装补全：转发到 install-completions.sh
# ==================================================================

echo ""
if [[ "$NO_COMPLETIONS" == "true" || "$SHELL_TARGET" == "none" ]]; then
    echo "[2/2] 跳过补全安装（--no-completions / --shell none）"
else
    echo "[2/2] 安装 shell 补全（shell=$SHELL_TARGET, dest-base=$DEST_BASE）..."
    echo ""
    # shellcheck disable=SC2086
    "$COMPLETIONS_SCRIPT" --shell "$SHELL_TARGET" --dest-dir "$DEST_BASE"
fi

# ==================================================================
# 3. 激活提示
# ==================================================================

echo ""
echo "=== 安装完成 ==="
echo ""
echo "yzrws 入口：$DEST_BIN"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "⚠ $BIN_DIR 不在当前 PATH 中，临时启用："
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    echo ""
    echo "永久启用（按 shell 选其一）："
    echo "    bash:  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc"
    echo "    zsh:   echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc"
    echo "    fish:  fish_add_path $BIN_DIR"
fi
echo ""
echo "验证：yzrws --help"
