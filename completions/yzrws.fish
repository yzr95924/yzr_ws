# fish completion for yzrws
#
# 支持顶层命令 + 二级 / 三级子命令（create workitem / model provider add / 等）
# 的 Tab 补全。workitem 名、provider 名、引擎名等动态值在补全时实时从
# workspace 目录与 provider.json 读取——无需 yzrws 自身暴露额外接口。
#
# 安装方式：复制到 ~/.config/fish/completions/yzrws.fish，重启 fish；
# 或运行 scripts/install-completions.sh。
#
# 防御性补全原则（与 doc/script_design.md "install-completions.sh" 节对齐）：
#   - 顶层子命令仅在 "尚未输入任何子命令" 时被补全
#     （__fish_use_subcommand），避免与二级菜单冲突
#   - 二级子命令的 complete 规则用
#     "__fish_seen_subcommand_from <父> and not __fish_seen_subcommand_from <子>"
#     模式——既要求父级已输入，又排除已输入过的子命令
#   - 多参"包含"条件必须用 `; and` 显式 AND：
#     `__fish_seen_subcommand_from A B C` 实际是 OR 语义（任一匹配即返回
#     true），写成"model provider"会让"yzrws model <Tab>"也命中，
#     错误地补出 add/list/remove/set-default。正确写法：
#     `__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider`
#   - 多参"排除"条件保持原样（OR + not 仍是"任一已见就排除"）
#   - value-taking flag 加 -r 标记（--engine -r -a ...），fish 自动跳过
#     flag value 的位置参数计数，不会污染后续 dispatch
#   - 已注册 engine / 已配置 Provider / 已存在 workitem 等动态值只在
#     对应位置（_yzrws_engines / _yzrws_providers / _yzrws_workitems）
#     被调用，越界场景不出现

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

# --agent-type 候选值：在 engine 列表基础上加特殊值 "all"（兼容所有 engine）
function __yzrws_agent_type_values
    echo all
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

# yzrws start --engine
complete -c yzrws -n "__fish_seen_subcommand_from start" -l engine -s e -r -a "(__yzrws_engines)" -d "指定引擎（创建或切换时使用）"

# ==================================================================
# yzrws model ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from provider" -a provider -d "管理 Provider（连接信息、默认 Provider 等）"

# yzrws model provider ...
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and not __fish_seen_subcommand_from add list remove set-default" -a "add" -d "添加一个 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and not __fish_seen_subcommand_from add list remove set-default" -a "list" -d "列出已配置 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and not __fish_seen_subcommand_from add list remove set-default" -a "remove" -d "删除 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and not __fish_seen_subcommand_from add list remove set-default" -a "set-default" -d "切换默认 Provider"

# yzrws model provider add
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l name -r -d "Provider 名称"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l base-url -r -d "API 端点 URL"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l auth-key -r -d "认证密钥"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l model -r -d "默认模型名称"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l agent-type -r -a "(__yzrws_agent_type_values)" -d "该 provider 兼容的 engine（可多次指定；'all' 表示全部）"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l set-default -d "强制将新 Provider 设为默认"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from add" -l yes -s y -d "同名 Provider 存在时跳过确认直接覆盖"

# yzrws model provider list  （无 flag / 位置参数）
# yzrws model provider remove <name> [-y]
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from remove" -fa "(__yzrws_providers)"
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from remove" -l yes -s y -d "跳过确认直接删除"

# yzrws model provider set-default <name>
complete -c yzrws -n "__fish_seen_subcommand_from model; and __fish_seen_subcommand_from provider; and __fish_seen_subcommand_from set-default" -fa "(__yzrws_providers)"

# ==================================================================
# yzrws workitem ...
# ==================================================================
#
# 守卫 `and not __fish_seen_subcommand_from create`：
#   `workitem` 既是顶层子命令，也是 `create` 的二级子命令。`__fish_seen_subcommand_from`
#   是 OR 语义——只要 `workitem` 出现在命令行任意位置就命中。如果不加 create
#   排除，下方 5 条 `yzrws workitem <subcmd>` 规则会在
#   `yzrws create workitem <Tab>` 时也触发，错误地列出 set-model/show 等
#   本不该出现的位置。
#
# create workitem 的反向（yzrws create workitem 下应只见 --engine/--start）
# 已经天然正确：那些规则用 `__fish_seen_subcommand_from create; and
# __fish_seen_subcommand_from workitem`，要求 create 必须出现，所以
# 顶层 `yzrws workitem ...` 不会触发它们。

complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "set-model" -d "把 workitem 绑定到某个 Provider"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "unset-model" -d "解除 workitem 的 Provider 绑定"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "show" -d "展示 workitem 完整配置与生效模型"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "set-outline" -d "为 workitem 启用 Outline MCP"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and not __fish_seen_subcommand_from set-model unset-model show set-outline unset-outline" -a "unset-outline" -d "解除 workitem 的 Outline MCP 引用"

# yzrws workitem set-model <name> --provider <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from set-model" -fa "(__yzrws_workitems)"
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from set-model" -l provider -r -a "(__yzrws_providers)" -d "Provider 名称（必须已配置）"

# yzrws workitem unset-model <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from unset-model" -fa "(__yzrws_workitems)"

# yzrws workitem show <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from show" -fa "(__yzrws_workitems)"

# yzrws workitem set-outline <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from set-outline" -fa "(__yzrws_workitems)"

# yzrws workitem unset-outline <name>
complete -c yzrws -n "__fish_seen_subcommand_from workitem; and not __fish_seen_subcommand_from create; and __fish_seen_subcommand_from unset-outline" -fa "(__yzrws_workitems)"

# ==================================================================
# yzrws outline ...
# ==================================================================

complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a add -d "添加 Outline Wiki 连接配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a show -d "展示当前 Outline 配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a update -d "更新 Outline 配置"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and not __fish_seen_subcommand_from add show update remove" -a remove -d "删除 Outline 配置"

# yzrws outline add
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from add" -l endpoint -r -d "Outline 实例 URL"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from add" -l auth-token -r -d "Outline API key"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from add" -l yes -s y -d "跳过确认提示"

# yzrws outline show  （无 flag / 位置参数）

# yzrws outline update
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from update" -l endpoint -r -d "新的 Outline 实例 URL"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from update" -l auth-token -r -d "新的 Outline API key"
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from update" -l yes -s y -d "跳过确认提示"

# yzrws outline remove
complete -c yzrws -n "__fish_seen_subcommand_from outline; and __fish_seen_subcommand_from remove" -l yes -s y -d "跳过确认提示"
