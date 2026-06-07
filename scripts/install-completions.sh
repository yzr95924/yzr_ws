#!/usr/bin/env bash
# install-completions.sh — 安装 yzrws 的 shell 补全脚本
#
# 默认根据 $SHELL 推断目标 shell，并把补全文件复制到该 shell 的标准补全目录：
#   - bash:  ~/.local/share/bash-completion/completions/yzrws
#   - zsh:   ~/.zsh/completions/_yzrws
#   - fish:  ~/.config/fish/completions/yzrws.fish
#
# 复制到这些位置后，多数发行版的现代 bash-completion / fish / 配置好 $fpath 的
# zsh 都无需额外步骤即可使用——少数情况请参考下方"激活提示"。
#
# 用法：
#   ./scripts/install-completions.sh                       # 按 $SHELL 自动检测
#   ./scripts/install-completions.sh --shell bash          # 显式指定 shell
#   ./scripts/install-completions.sh --shell all           # 一次性为所有 shell 安装
#   ./scripts/install-completions.sh --uninstall           # 卸载已安装的补全
#   ./scripts/install-completions.sh --dest-dir <path> ... # 安装到非默认根目录
#                                                         # （默认 $HOME，用于包管理 / 测试）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPLETIONS_DIR="$REPO_ROOT/completions"

# 解析参数
SHELL_TARGET=""
UNINSTALL=false
DEST_BASE="$HOME"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --shell)
            SHELL_TARGET="${2:-}"
            shift 2
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --dest-dir)
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

# 校验 DEST_BASE
if [[ -z "$DEST_BASE" ]]; then
    echo "错误：--dest-dir 不能为空" >&2
    exit 2
fi

# 推断默认 shell
if [[ -z "$SHELL_TARGET" ]]; then
    SHELL_TARGET=$(basename "${SHELL:-/bin/bash}")
fi

# 安装/卸载函数。每个 shell 一段独立逻辑。
install_bash() {
    local dst="$DEST_BASE/.local/share/bash-completion/completions/yzrws"
    local src="$COMPLETIONS_DIR/yzrws.bash"
    if $UNINSTALL; then
        if [[ -f "$dst" ]]; then
            rm -f "$dst"
            echo "[bash] 已删除 $dst"
        else
            echo "[bash] 未发现已安装的补全（$dst），跳过"
        fi
        return
    fi
    if [[ ! -f "$src" ]]; then
        echo "[bash] 缺少 $src" >&2
        return 1
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "[bash] 已安装 $dst"
}

install_zsh() {
    local dst_dir="$DEST_BASE/.zsh/completions"
    local dst="$dst_dir/_yzrws"
    local src="$COMPLETIONS_DIR/_yzrws"
    if $UNINSTALL; then
        if [[ -f "$dst" ]]; then
            rm -f "$dst"
            echo "[zsh] 已删除 $dst"
        else
            echo "[zsh] 未发现已安装的补全（$dst），跳过"
        fi
        return
    fi
    if [[ ! -f "$src" ]]; then
        echo "[zsh] 缺少 $src" >&2
        return 1
    fi
    mkdir -p "$dst_dir"
    cp "$src" "$dst"
    echo "[zsh] 已安装 $dst"
}

install_fish() {
    local dst="$DEST_BASE/.config/fish/completions/yzrws.fish"
    local src="$COMPLETIONS_DIR/yzrws.fish"
    if $UNINSTALL; then
        if [[ -f "$dst" ]]; then
            rm -f "$dst"
            echo "[fish] 已删除 $dst"
        else
            echo "[fish] 未发现已安装的补全（$dst），跳过"
        fi
        return
    fi
    if [[ ! -f "$src" ]]; then
        echo "[fish] 缺少 $src" >&2
        return 1
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "[fish] 已安装 $dst"
}

# 按目标 shell 分发
case "$SHELL_TARGET" in
    bash)
        install_bash
        ;;
    zsh)
        install_zsh
        ;;
    fish)
        install_fish
        ;;
    all)
        install_bash || true
        install_zsh || true
        install_fish || true
        ;;
    *)
        echo "不支持的 shell: $SHELL_TARGET（请使用 bash / zsh / fish / all）" >&2
        exit 1
        ;;
esac

# 激活提示
if ! $UNINSTALL; then
    echo ""
    echo "激活提示："
    case "$SHELL_TARGET" in
        bash)
            echo "  重新加载 shell 或执行："
            echo "    source ~/.local/share/bash-completion/completions/yzrws"
            echo "  确认 bash-completion 已加载（多数发行版默认加载）："
            echo "    complete -p | head -1    # 应能看到已注册的补全"
            ;;
        zsh)
            echo "  确认 ~/.zshrc 中包含以下行："
            echo "    fpath=(~/.zsh/completions \$fpath)"
            echo "    autoload -U compinit && compinit"
            echo "  然后重新加载 shell：exec zsh"
            ;;
        fish)
            echo "  无需额外配置——fish 启动时会自动加载。"
            echo "  重新加载 shell：exec fish"
            ;;
        all)
            echo "  各 shell 激活步骤见上方分项提示。"
            ;;
    esac
fi
