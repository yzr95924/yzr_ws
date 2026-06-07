# fish completion for yzrws
#
# 支持顶层命令 + 二级 / 三级子命令（create workitem / model provider add / 等）
# 的 Tab 补全。workitem 名、provider 名、引擎名等动态值在补全时实时从
# workspace 目录与 provider.json 读取——无需 yzrws 自身暴露额外接口。
#
# 安装方式：复制到 ~/.config/fish/completions/yzrws.fish，重启 fish；
# 或运行 scripts/install-completions.sh。

# ==================================================================
# 公共 helper
# ==================================================================

# 解析 workspace 路径，对齐 yzrws.paths.get_workspace_path()：
# 优先 YZR_WORKSPACE（空串视为未设置），否则默认 ~/yzr_workspace。
function __yzrws_workspace_path
    set -l raw (string trim -- "$YZR_WORKSPACE")
    if test -z "$raw"
        set raw "$HOME/yzr_workspace"
    end
    set raw (string replace -r '^~' "$HOME" -- "$raw")
    set raw (string replace -r '/$' '' -- "$raw")
    echo "$raw"
end

# 列出 workspace 下所有工作项目录名（子目录）。
function __yzrws_workitems
    set -l ws (__yzrws_workspace_path)
    if not test -d "$ws"
        return
    end
    # 不含 .config 等隐藏目录——与 workitem 命名规则对齐（必须以字母/数字开头）
    for d in (command ls -1 "$ws" 2>/dev/null)
        if test -d "$ws/$d"
            echo "$d"
        end
    end
end

# 列出 workspace provider.json 中已配置的 Provider 名称。
# fish 不支持 bash 风格的 heredoc；改用 -c 传脚本。
function __yzrws_providers
    set -l ws (__yzrws_workspace_path)
    set -l provider_json "$ws/.config/provider.json"
    if not test -r "$provider_json"
        return
    end
    python3 -c "
import json, sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        data = json.load(f)
    providers = data.get('providers', {})
    if isinstance(providers, dict):
        for name in providers:
            print(name)
except (OSError, ValueError):
    sys.exit(0)
" "$provider_json" 2>/dev/null
end

# 已注册的 engine 列表（与 src/yzrws/engine/__init__.py 保持一致）。
function __yzrws_engines
    echo claude-code
    echo opencode
end

# ==================================================================
# 关闭默认 file completion（由各规则按需启用）
# ==================================================================

complete -c yzrws -f

# ==================================================================
# 顶层子命令
# ==================================================================

complete -c yzrws -n "__fish_use_subcommand" -a init -d "初始化 workspace 目录结构"
complete -c yzrws -n "__fish_use_subcommand" -a create -d "创建工作项等资源"
complete -c yzrws -n "__fish_use_subcommand" -a list -d "列举所有工作项及其元数据"
complete -c yzrws -n "__fish_use_subcommand" -a start -d "打开工作项并启动 Agent 会话"
complete -c yzrws -n "__fish_use_subcommand" -a model -d "管理模型与 Provider 配置"
complete -c yzrws -n "__fish_use_subcommand" -a workitem -d "管理 workitem 级别配置"
complete -c yzrws -n "__fish_use_subcommand" -a outline -d "管理 Outline Wiki MCP 配置"

# ==================================================================
# yzrws create ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from create; and not __fish_seen_subcommand_from workitem" -a workitem -d "创建一个新的工作项"

# yzrws create workitem <name> [--engine ...] [--start]
complete -c yzrws -n "__fish_seen_subcommand_from create; and __fish_seen_subcommand_from workitem" -l engine -s e -r -a "(__yzrws_engines)" -d "指定 Agent 引擎（覆盖全局默认）"
complete -c yzrws -n "__fish_seen_subcommand_from create; and __fish_seen_subcommand_from workitem" -l start -d "创建完成后自动执行 yzrws start"

# ==================================================================
# yzrws list  /  yzrws init  无子命令
# ==================================================================

# 已通过 -f 关闭 file completion；无规则时不会补全任何东西，符合预期

# ==================================================================
# yzrws start ...
# ==================================================================

# yzrws start <name>
complete -c yzrws -n "__fish_seen_subcommand_from start; and not __fish_seen_subcommand_from -l" -fa "(__yzrws_workitems)"

# yzrws start --engine / --new
complete -c yzrws -n "__fish_seen_subcommand_from start" -l engine -s e -r -a "(__yzrws_engines)" -d "指定引擎（创建或切换时使用）"
complete -c yzrws -n "__fish_seen_subcommand_from start" -l new -d "强制启动新会话（不恢复历史）"

# ==================================================================
# yzrws model ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from provider" -a provider -d "管理 Provider（连接信息、默认 Provider 等）"

# yzrws model provider ...
complete -c yzrws -n "__fish_seen_subcommand_from model provider; and not __fish_seen_subcommand_from add list remove set-default" -a "add" -d "添加一个 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model provider; and not __fish_seen_subcommand_from add list remove set-default" -a "list" -d "列出已配置 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model provider; and not __fish_seen_subcommand_from add list remove set-default" -a "remove" -d "删除 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model provider; and not __fish_seen_subcommand_from add list remove set-default" -a "set-default" -d "切换默认 Provider"

# yzrws model provider add
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l name -r -d "Provider 名称"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l base-url -r -d "API 端点 URL"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l auth-key -r -d "认证密钥"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l model -r -d "默认模型名称"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l agent-type -r -a "(__yzrws_engines)" -d "该 provider 兼容的 engine（可多次指定）"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l set-default -d "强制将新 Provider 设为默认"
complete -c yzrws -n "__fish_seen_subcommand_from model provider add" -l yes -s y -d "同名 Provider 存在时跳过确认直接覆盖"

# yzrws model provider list  （无 flag / 位置参数）
# yzrws model provider remove <name> [-y]
complete -c yzrws -n "__fish_seen_subcommand_from model provider remove" -fa "(__yzrws_providers)"
complete -c yzrws -n "__fish_seen_subcommand_from model provider remove" -l yes -s y -d "跳过确认直接删除"

# yzrws model provider set-default <name>
complete -c yzrws -n "__fish_seen_subcommand_from model provider set-default" -fa "(__yzrws_providers)"

# ==================================================================
# yzrws workitem ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "set-model" -d "把 workitem 绑定到某个 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "unset-model" -d "解除 workitem 的 Provider 绑定"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "show" -d "展示 workitem 完整配置与生效模型"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "set-outline" -d "为 workitem 启用 Outline MCP"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "unset-outline" -d "解除 workitem 的 Outline MCP 引用"

# yzrws workitem set-model <name> --provider <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem set-model" -fa "(__yzrws_workitems)"
complete -c yzrws -n "__fish_seen_subcommand_from workitem set-model" -l provider -r -a "(__yzrws_providers)" -d "Provider 名称（必须已配置）"

# yzrws workitem unset-model <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem unset-model" -fa "(__yzrws_workitems)"

# yzrws workitem show <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem show" -fa "(__yzrws_workitems)"

# yzrws workitem set-outline <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem set-outline" -fa "(__yzrws_workitems)"

# yzrws workitem unset-outline <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem unset-outline" -fa "(__yzrws_workitems)"

# ==================================================================
# yzrws outline ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a add -d "添加 Outline Wiki 连接配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a show -d "展示当前 Outline 配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a update -d "更新 Outline 配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a remove -d "删除 Outline 配置"

# yzrws outline add
complete -c yzrws -n "__fish_seen_subcommand_from outline add" -l endpoint -r -d "Outline 实例 URL"
complete -c yzrws -n "__fish_seen_subcommand_from outline add" -l auth-token -r -d "Outline API key"
complete -c yzrws -n "__fish_seen_subcommand_from outline add" -l yes -s y -d "跳过确认提示"

# yzrws outline show  （无 flag / 位置参数）

# yzrws outline update
complete -c yzrws -n "__fish_seen_subcommand_from outline update" -l endpoint -r -d "新的 Outline 实例 URL"
complete -c yzrws -n "__fish_seen_subcommand_from outline update" -l auth-token -r -d "新的 Outline API key"
complete -c yzrws -n "__fish_seen_subcommand_from outline update" -l yes -s y -d "跳过确认提示"

# yzrws outline remove
complete -c yzrws -n "__fish_seen_subcommand_from outline remove" -l yes -s y -d "跳过确认提示"
