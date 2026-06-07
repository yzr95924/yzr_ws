# bash completion for yzrws
#
# 支持 yzrws 顶层命令 + 二级 / 三级子命令（create workitem / model provider add / 等）
# 的 Tab 补全。文件名、provider 名、引擎名等动态值在补全时从 workspace 目录
# 与 provider.json 实时读取，无需 yzrws 自身暴露额外接口。
#
# 安装方式见 scripts/install-completions.sh，或参考 README.md "Shell 补全" 一节。

# ==================================================================
# 公共 helper
# ==================================================================

# 解析当前 workspace 路径，对齐 yzrws.paths.get_workspace_path() 的语义：
# 优先 YZR_WORKSPACE 环境变量（空串视为未设置），否则使用默认 ~/yzr_workspace。
# 返回值已展开 ~，调用方无需再处理。
_yzrws_workspace_path() {
    local raw="${YZR_WORKSPACE:-}"
    if [[ -z "${raw// /}" ]]; then
        raw="$HOME/yzr_workspace"
    fi
    # 展开 ~ 与 $HOME；去掉尾部 /，便于后续拼路径
    raw="${raw/#\~/$HOME}"
    printf '%s' "${raw%/}"
}

# 列出 workspace 下所有工作项目录名（子目录）。不校验 workitem.json 是否存在——
# yzrws list 的实现也仅做"是目录"的筛选。
_yzrws_workitems() {
    local ws
    ws="$(_yzrws_workspace_path)"
    [[ -d "$ws" ]] || return 0
    # 仅取直接子目录名（不包含 .config 等隐藏目录——与 workitem 名称
    # 命名规则对齐：必须以小写字母/数字开头）；-L 不展开链接；
    # LC_ALL=C 让排序稳定
    local name
    while IFS= read -r name; do
        [[ -d "$ws/$name" ]] && printf '%s\n' "$name"
    done < <(LC_ALL=C command ls -1 "$ws" 2>/dev/null)
}

# 列出 workspace provider.json 中已配置的 Provider 名称。
# provider.json 缺失或解析失败时静默返回空——补全失败不应阻断主命令。
_yzrws_providers() {
    local ws provider_json
    ws="$(_yzrws_workspace_path)"
    provider_json="$ws/.config/provider.json"
    [[ -r "$provider_json" ]] || return 0
    # 用 python3 解析 JSON：jq 不一定安装；python3 是 yzrws 自身依赖。
    # providers 是一个 object，键为 Provider 名。
    python3 - "$provider_json" <<'PYEOF' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    providers = data.get("providers", {})
    if isinstance(providers, dict):
        for name in providers:
            print(name)
except (OSError, ValueError):
    sys.exit(0)
PYEOF
}

# 已注册的 engine 列表。当前在 src/yzrws/engine/__init__.py 静态注册，
# 写死在补全里——新增 engine 时需同步更新本函数。
_yzrws_engines() {
    printf '%s\n' claude-code opencode
}

# ==================================================================
# flag 补全：按当前已确定的位置参数生成对应子命令的 flag 列表
# ==================================================================

_yzrws_complete_flags() {
    local cur="$1"; shift
    local positional=("$@")
    local n=${#positional[@]}
    local flags=""

    case "$n" in
        0) flags="-h --help" ;;
        1)
            case "${positional[0]}" in
                init) flags="-h --help" ;;
                list) flags="-h --help" ;;
                create) flags="-h --help" ;;
                start) flags="-h --help --engine -e --new" ;;
                model) flags="-h --help" ;;
                workitem) flags="-h --help" ;;
                outline) flags="-h --help" ;;
            esac
            ;;
        2)
            case "${positional[0]}.${positional[1]}" in
                create.workitem) flags="-h --help --engine --start" ;;
                model.provider) flags="-h --help" ;;
                workitem.set-model) flags="-h --help --provider" ;;
                workitem.unset-model) flags="-h --help" ;;
                workitem.show) flags="-h --help" ;;
                workitem.set-outline) flags="-h --help" ;;
                workitem.unset-outline) flags="-h --help" ;;
                outline.add) flags="-h --help --endpoint --auth-token -y --yes" ;;
                outline.show) flags="-h --help" ;;
                outline.update) flags="-h --help --endpoint --auth-token -y --yes" ;;
                outline.remove) flags="-h --help -y --yes" ;;
            esac
            ;;
        3)
            case "${positional[0]}.${positional[1]}.${positional[2]}" in
                model.provider.add)
                    flags="-h --help --name --base-url --auth-key --model --agent-type --set-default -y --yes"
                    ;;
                model.provider.list) flags="-h --help" ;;
                model.provider.remove) flags="-h --help -y --yes" ;;
                model.provider.set-default) flags="-h --help" ;;
            esac
            ;;
    esac

    if [[ -n "$flags" ]]; then
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
    else
        COMPREPLY=()
    fi
}

# ==================================================================
# 位置参数补全
# ==================================================================

# yzrws <command> 当前在第一个位置
_yzrws_dispatch_1() {
    local cmd="$1" cur="$2"
    case "$cmd" in
        init|list) COMPREPLY=() ;;           # 无位置参数
        create)
            COMPREPLY=( $(compgen -W "workitem" -- "$cur") )
            ;;
        start)
            COMPREPLY=( $(compgen -W "$(_yzrws_workitems)" -- "$cur") )
            ;;
        model)
            COMPREPLY=( $(compgen -W "provider" -- "$cur") )
            ;;
        workitem)
            COMPREPLY=( $(compgen -W "set-model unset-model show set-outline unset-outline" -- "$cur") )
            ;;
        outline)
            COMPREPLY=( $(compgen -W "add show update remove" -- "$cur") )
            ;;
        *) COMPREPLY=() ;;
    esac
}

# yzrws <cmd> <sub> 当前在第二个位置
_yzrws_dispatch_2() {
    local cmd="$1" sub="$2" cur="$3"
    case "$cmd.$sub" in
        # yzrws create workitem <name>
        # 故意不补全已有 workitem 名——create 期望创建新名
        create.workitem) COMPREPLY=() ;;

        # start 不再有位置参数（第一位置已在 _yzrws_dispatch_1 处理）
        start.*) COMPREPLY=() ;;

        # yzrws model provider <subcmd>
        model.provider)
            COMPREPLY=( $(compgen -W "add list remove set-default" -- "$cur") )
            ;;

        # yzrws workitem <set-model|unset-model|show|...> <name>
        workitem.set-model|\
        workitem.unset-model|\
        workitem.show|\
        workitem.set-outline|\
        workitem.unset-outline)
            COMPREPLY=( $(compgen -W "$(_yzrws_workitems)" -- "$cur") )
            ;;

        # yzrws outline <add|show|update|remove>  无位置参数
        outline.*) COMPREPLY=() ;;

        *) COMPREPLY=() ;;
    esac
}

# yzrws <cmd> <sub> <leaf> 当前在第三个位置
_yzrws_dispatch_3() {
    local cmd="$1" sub="$2" leaf="$3" cur="$4"
    case "$cmd.$sub.$leaf" in
        # yzrws model provider remove <name> / set-default <name>
        model.provider.remove|\
        model.provider.set-default)
            COMPREPLY=( $(compgen -W "$(_yzrws_providers)" -- "$cur") )
            ;;

        # 其他三级子命令无位置参数
        *) COMPREPLY=() ;;
    esac
}

# ==================================================================
# 特殊值：--engine / --agent-type / --provider 后的补全
# ==================================================================

_yzrws_handle_value_flags() {
    local prev_flag="$1" cur="$2"
    case "$prev_flag" in
        --engine|-e)
            COMPREPLY=( $(compgen -W "$(_yzrws_engines)" -- "$cur") )
            return 0
            ;;
        --agent-type)
            COMPREPLY=( $(compgen -W "$(_yzrws_engines)" -- "$cur") )
            return 0
            ;;
        --provider)
            COMPREPLY=( $(compgen -W "$(_yzrws_providers)" -- "$cur") )
            return 0
            ;;
    esac
    return 1
}

# ==================================================================
# 主入口
# ==================================================================

_yzrws() {
    local cur prev words cword
    # 兼容 bash-completion 缺失的环境（部分发行版默认未装）
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion || return
    else
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    fi

    # flag 后的值补全（仅当 cur 不是 - 开头）
    if [[ "$cur" != -* ]]; then
        if _yzrws_handle_value_flags "$prev" "$cur"; then
            return
        fi
    fi

    # 解析位置参数序列（去掉所有 flag）
    local positional=()
    local j
    for ((j = 1; j < cword; j++)); do
        if [[ "${words[$j]}" != -* ]]; then
            positional+=("${words[$j]}")
        fi
    done
    local n=${#positional[@]}

    # flag 名补全
    if [[ "$cur" == -* ]]; then
        _yzrws_complete_flags "$cur" "${positional[@]}"
        return
    fi

    # 位置参数补全
    case "$n" in
        0) COMPREPLY=( $(compgen -W "init create list start model workitem outline" -- "$cur") ) ;;
        1) _yzrws_dispatch_1 "${positional[0]}" "$cur" ;;
        2) _yzrws_dispatch_2 "${positional[0]}" "${positional[1]}" "$cur" ;;
        3) _yzrws_dispatch_3 "${positional[0]}" "${positional[1]}" "${positional[2]}" "$cur" ;;
        *) COMPREPLY=() ;;
    esac
}

complete -F _yzrws yzrws
