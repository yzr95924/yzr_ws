#!/usr/bin/env bash
# uninstall.sh — 卸载 yzrws 主命令与已安装的 shell 补全
#
# 职责：
#   1. 删除 <prefix>/bin/yzrws 软链接（默认 ~/.local/bin/yzrws）
#   2. 调用 install-completions.sh --uninstall 移除已安装的补全
#
# 两者都设计为幂等：未发现目标时静默跳过，重复运行安全。
#
# 用法：
#   ./scripts/uninstall.sh                        # 卸载主命令 + 全部补全（默认）
#   ./scripts/uninstall.sh --prefix /opt/yzrws    # 卸载其他 prefix 下的内容
#   ./scripts/uninstall.sh --bin-dir ~/.local/bin # 仅指定 bin 目录
#   ./scripts/uninstall.sh --shell bash           # 只卸某种 shell 的补全（bash|zsh|fish）
#   ./scripts/uninstall.sh --no-completions       # 仅卸载主命令，保留补全
#   ./scripts/uninstall.sh --dest-base /tmp/...   # 测试场景：补全装在 /tmp/... 时也能定位

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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
            sed -n '2,15p' "$0"
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
if [[ -n "$SHELL_TARGET" ]] && [[ "$SHELL_TARGET" != "bash" && "$SHELL_TARGET" != "zsh" && "$SHELL_TARGET" != "fish" ]]; then
    echo "错误：--shell 只接受 bash / zsh / fish（默认卸全部，省略此参数）" >&2
    exit 2
fi
if [[ "$NO_COMPLETIONS" == "true" && -n "$SHELL_TARGET" ]]; then
    echo "错误：--no-completions 与 --shell 互斥" >&2
    exit 2
fi

# 由 --prefix 推导默认 --bin-dir
if [[ -z "$BIN_DIR" ]]; then
    BIN_DIR="$PREFIX/bin"
fi
if [[ -z "$BIN_DIR" ]]; then
    echo "错误：无法确定 bin 目录" >&2
    exit 2
fi

# ==================================================================
# 1. 卸载主命令
# ==================================================================

DEST_BIN="$BIN_DIR/yzrws"

echo "=== yzrws 卸载 ==="
echo ""
echo "[1/2] 移除主命令..."
echo "  目标: $DEST_BIN"

if [[ ! -e "$DEST_BIN" && ! -L "$DEST_BIN" ]]; then
    echo "  未发现已安装的 yzrws，跳过"
else
    if [[ -L "$DEST_BIN" ]]; then
        # 二次校验：链接是否指向本仓库的 bin/yzrws，避免误删他处同名文件
        current_target=$(readlink "$DEST_BIN")
        expected_prefix="$REPO_ROOT/bin/yzrws"
        if [[ "$current_target" != "$expected_prefix" ]]; then
            echo "  ⚠ 警告：$DEST_BIN 是符号链接，但目标不是 $expected_prefix" >&2
            echo "    实际目标: $current_target" >&2
            echo "    为安全起见，本次不删除；如确认无误可手动 rm $DEST_BIN" >&2
        else
            rm -f "$DEST_BIN"
            echo "  ✓ 已删除软链接"
        fi
    else
        echo "  错误：$DEST_BIN 不是符号链接，可能是手动复制的实体文件" >&2
        echo "  为安全起见，本次不删除；如确认无误可手动 rm $DEST_BIN" >&2
    fi
fi

# ==================================================================
# 2. 卸载补全：转发到 install-completions.sh --uninstall
# ==================================================================

echo ""
if [[ "$NO_COMPLETIONS" == "true" ]]; then
    echo "[2/2] 跳过补全卸载（--no-completions）"
elif [[ ! -x "$COMPLETIONS_SCRIPT" ]]; then
    echo "[2/2] 跳过补全卸载：缺少 $COMPLETIONS_SCRIPT"
else
    # 缺省（SHELL_TARGET 空）：转发 --shell all，卸 bash + zsh + fish
    # 显式指定 SHELL_TARGET：仅卸该 shell 的补全
    effective_target="${SHELL_TARGET:-all}"
    echo "[2/2] 卸载 shell 补全（shell=${effective_target}, dest-base=${DEST_BASE}）..."
    echo ""
    "$COMPLETIONS_SCRIPT" --shell "$effective_target" --dest-dir "$DEST_BASE" --uninstall
fi

echo ""
echo "=== 卸载完成 ==="
