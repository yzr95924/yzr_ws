"""yzrws model provider 子命令实现。

设计参考 doc/provider_design.md。
提供 4 个子命令：add / list / remove / set-default。
这些函数被 commands/model.py 调度，不直接注册到 REGISTRY。

所有 Provider 配置统一存放在 workspace 下的 <workspace>/.config/provider.json。
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from yzrws import paths
from yzrws.output import (
    STATUS_ERROR,
    STATUS_WARN,
    print_banner,
    print_failure,
    print_provider_added,
    print_provider_duplicate_confirm,
    print_provider_empty,
    print_provider_list_header,
    print_provider_list_row,
    print_provider_removed,
    print_provider_workspace_not_initialized,
    print_unused_provider_warning,
    print_user_aborted,
)
from yzrws.provider import (
    Provider,
    ProviderConfigError,
    add_provider,
    get_workspace_provider_path,
    is_valid_base_url,
    is_valid_name,
    load_config,
    remove_provider as remove_provider_from_config,
    save_config,
    set_default as set_default_in_config,
)

# 顶层 --help 显示的简短描述（被 model.py 透传）
HELP = "管理模型 Provider 配置"

# Provider 名称命名规则说明（用于错误提示）
_NAME_RULE_LINES = (
    "  • 只允许小写字母、数字、连字符（-）和下划线（_）",
    "  • 长度 1-32 个字符",
    "  • 必须以小写字母或数字开头",
    "  • 示例：anthropic, my-gateway, gateway_v2",
)


# ==================================================================
# 业务：load / 路径包装
# ==================================================================


def _resolve_provider_path(workspace_path: Path) -> Path:
    """确定本次操作的 provider.json 路径，要求 workspace 已初始化。

    Raises:
        _AbortError: 前置检查失败，要求退出当前子命令。
    """
    if not workspace_path.is_dir() or not (workspace_path / "metadata.json").is_file():
        print_provider_workspace_not_initialized(workspace_path)
        raise _AbortError
    return get_workspace_provider_path(workspace_path)


class _AbortError(Exception):
    """内部信号：用户中止或前置检查失败，要求退出当前子命令。"""


# ==================================================================
# yzrws model provider list
# ==================================================================


def run_list(args: argparse.Namespace) -> int:
    """实现 `yzrws model provider list`."""
    workspace_path = paths.get_workspace_path()
    try:
        provider_path = _resolve_provider_path(workspace_path)
    except _AbortError:
        return 1

    try:
        config = load_config(provider_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    print_banner("Provider 列表")
    print()
    if not config.providers:
        print_provider_empty()
        return 0

    from yzrws.engine import list_engines

    engines = list_engines()

    col_widths = _compute_list_col_widths(config, engines)
    print_provider_list_header(col_widths)
    for name in config.provider_names():
        p = config.providers[name]
        agent_types = p.resolved_agent_types(engines)
        agent_types_display = (
            "all" if set(agent_types) >= set(engines) else ", ".join(agent_types)
        )
        print_provider_list_row(
            name=p.name,
            base_url=p.base_url,
            model=p.model,
            agent_types_display=agent_types_display,
            is_default=(config.default == name),
            col_widths=col_widths,
        )
    return 0


# ==================================================================
# yzrws model provider add
# ==================================================================


def run_add(args: argparse.Namespace) -> int:
    """实现 `yzrws model provider add [--name ... --base-url ... --auth-key ... --model ...]`。

    行为（对齐 doc/provider_design.md §创建流程）：
      1. 校验 workspace 已初始化
      2. 收集 4 个字段（交互式或 CLI 参数），执行校验
      3. 读现有配置 → 写入新 Provider（重复时确认）→ 落盘
      4. 第一个 Provider 自动标记为 default；显式 --set-default 也可强制
    """
    workspace_path = paths.get_workspace_path()
    try:
        target_path = _resolve_provider_path(workspace_path)
    except _AbortError:
        return 1

    print_banner("添加 Provider")
    print()
    print(f"目标文件：{target_path}")
    print()

    try:
        new_provider = _collect_provider_fields(args, target_path)
    except _AbortError:
        return 1

    try:
        config = load_config(target_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    if new_provider.name in config.providers:
        if not args.yes and not _confirm_overwrite(new_provider.name, target_path):
            print_user_aborted("添加 Provider")
            return 1

    new_config = add_provider(
        config,
        new_provider,
        set_as_default=args.set_default,
    )

    save_config(target_path, new_config)
    is_default = new_config.default == new_provider.name
    print_provider_added(
        name=new_provider.name,
        is_default=is_default,
        is_first=config.is_empty(),
        set_default_flag=args.set_default,
    )
    return 0


def _collect_provider_fields(args: argparse.Namespace, target_path: Path) -> Provider:
    """根据 CLI 参数 + 交互式输入收集 Provider 字段并校验。"""
    name = _prompt_or_arg("Provider 名称", args.name, validator=is_valid_name)
    base_url = _prompt_or_arg("Base URL", args.base_url, validator=is_valid_base_url)
    auth_key = _prompt_secret("Auth Key", args.auth_key)
    model = _prompt_or_arg(
        "Model name", args.model, validator=lambda s: bool(s.strip())
    )

    # agent_types：CLI 多次 --agent-type 优先；否则进入交互式 prompt
    from yzrws.engine import list_engines

    engines = list_engines()
    agent_types = _collect_agent_types(args.agent_types, engines)

    return Provider(
        name=name,
        base_url=base_url,
        auth_key=auth_key,
        model=model,
        agent_types=agent_types,
    )


def _collect_agent_types(
    cli_values: list[str] | None,
    engines: list[str],
) -> list[str]:
    """收集 agent_types：CLI 多次 --agent-type > 缺省 = 交互式 prompt。

    CLI 分支走 `_validate_agent_types`；无 CLI 值时进入交互式 prompt。
    """
    if cli_values:
        return _validate_agent_types(cli_values, engines)
    return _prompt_agent_types(engines)


def _validate_agent_types(
    cli_values: list[str],
    engines: list[str],
) -> list[str]:
    """校验并规范化 CLI 提供的 agent_types 列表。

    处理 "all" 特殊值：
      - 单独使用（仅 --agent-type all）：与不传此参数等价，返回空列表
      - 与具体 engine 混用：报错（语义模糊）
    """
    from yzrws.provider import AGENT_TYPE_ALL

    has_all = AGENT_TYPE_ALL in cli_values
    non_all = [v for v in cli_values if v != AGENT_TYPE_ALL]

    if has_all and non_all:
        print(
            f"[{STATUS_ERROR}] --agent-type {AGENT_TYPE_ALL} 不能与具体 engine 混用；"
            f"收到的非 '{AGENT_TYPE_ALL}' 值：{non_all}"
        )
        raise _AbortError

    if has_all:
        # 单独使用 'all'：与缺省等价，返回空列表让 Provider.agent_types
        # 缺省值生效（即"全部"），且 JSON 中不写 agent_types 字段
        return []

    # 常规分支：每个值都必须在已注册 engine 列表中
    invalid = [v for v in non_all if not _is_valid_agent_type_str(v, engines)]
    if invalid:
        print(
            f"[{STATUS_ERROR}] 未知的 --agent-type：{invalid}；"
            f"当前支持的 engine：{engines}（或特殊值 '{AGENT_TYPE_ALL}'）"
        )
        raise _AbortError
    # 去重保持顺序
    seen: set[str] = set()
    deduped: list[str] = []
    for v in non_all:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def _prompt_agent_types(engines: list[str]) -> list[str]:
    """交互式收集 agent_types（编号选择形式）。

    打印编号菜单：1) all + 已注册 engine 列表；用户输入编号（单选）或
    逗号分隔的编号组合（多选），留空默认 1（all）。

    'all' 与具体 engine 混用会被拒绝（语义模糊）。
    """
    from yzrws.provider import AGENT_TYPE_ALL

    # 菜单：1) all 在前，其后是已注册 engine
    options: list[str] = [AGENT_TYPE_ALL, *engines]

    print("Agent types:")
    for idx, name in enumerate(options, start=1):
        if name == AGENT_TYPE_ALL:
            print(f"  {idx}) {name}（兼容所有 engine）")
        else:
            print(f"  {idx}) {name}")

    label = "请选择（逗号分隔多个，回车默认 1）"

    try:
        raw = input(f"{label}: ").strip()
    except EOFError:
        print(f"\n[{STATUS_ERROR}] 输入中断", file=sys.stderr)
        raise _AbortError from None

    # 留空 → 默认 1 (all)
    if not raw:
        return []

    # 解析逗号分隔的编号
    tokens = [t.strip() for t in raw.split(",")]
    tokens = [t for t in tokens if t]  # 应对 ",," 等异常输入
    if not tokens:
        return []

    try:
        indices = [int(t) for t in tokens]
    except ValueError:
        print(f"[{STATUS_ERROR}] 输入必须是编号 1-{len(options)}（逗号分隔）：{raw!r}")
        raise _AbortError

    invalid_range = [i for i in indices if i < 1 or i > len(options)]
    if invalid_range:
        print(f"[{STATUS_ERROR}] 编号超出范围 1-{len(options)}：{invalid_range}")
        raise _AbortError

    # 编号 → 名字，去重保持顺序
    chosen: list[str] = []
    seen: set[int] = set()
    for i in indices:
        if i in seen:
            continue
        seen.add(i)
        chosen.append(options[i - 1])

    has_all = AGENT_TYPE_ALL in chosen
    non_all = [n for n in chosen if n != AGENT_TYPE_ALL]

    if has_all and non_all:
        print(
            f"[{STATUS_ERROR}] '{AGENT_TYPE_ALL}'（编号 1）不能与具体 engine 混用；"
            f"收到的非 '{AGENT_TYPE_ALL}' 值：{non_all}"
        )
        raise _AbortError

    if has_all:
        return []

    return non_all


def _is_valid_agent_type_str(name: str, engines: list[str]) -> bool:
    """校验 agent_type 字符串是否在已注册 engine 列表中。"""
    from yzrws.provider import is_valid_agent_type

    return is_valid_agent_type(name, engines)


def _prompt_or_arg(
    label: str,
    cli_value: str | None,
    *,
    validator,
) -> str:
    """从 CLI 参数取值；为空时进入交互式输入，使用 validator 校验。"""
    if cli_value:
        value = cli_value
    else:
        try:
            value = input(f"{label}: ").strip()
        except EOFError:
            print(f"\n[{STATUS_ERROR}] 输入中断", file=sys.stderr)
            raise _AbortError from None
    if not validator(value):
        print(f"[{STATUS_ERROR}] {label} 不合法：{value!r}")
        _print_name_rule_hint(label)
        raise _AbortError
    return value


def _prompt_secret(label: str, cli_value: str | None) -> str:
    """交互式隐藏输入 Auth Key；CLI 传值时回显提示但不要求隐藏。"""
    if cli_value:
        return cli_value
    try:
        # getpass 在不支持的终端上会退回到普通 input
        value = getpass.getpass(f"{label}: ")
    except (EOFError, KeyboardInterrupt):
        print(f"\n[{STATUS_ERROR}] 输入中断", file=sys.stderr)
        raise _AbortError from None
    if not value:
        print(f"[{STATUS_ERROR}] {label} 不能为空")
        raise _AbortError
    return value


def _print_name_rule_hint(label: str) -> None:
    """名称不合法时打印规则提示。其它字段只打印一行说明。"""
    if label == "Provider 名称":
        print("命名规则：")
        for line in _NAME_RULE_LINES:
            print(line)
    elif label == "Base URL":
        print(
            "Base URL 必须是合法 URL（包含 scheme 与 host），如 https://api.anthropic.com"
        )


def _confirm_overwrite(name: str, target_path: Path) -> bool:
    """同名 Provider 已存在时，提示用户确认覆盖。"""
    return print_provider_duplicate_confirm(name, target_path)


# ==================================================================
# yzrws model provider remove
# ==================================================================


def run_remove(args: argparse.Namespace) -> int:
    """实现 `yzrws model provider remove <name> [-y]`."""
    workspace_path = paths.get_workspace_path()
    try:
        target_path = _resolve_provider_path(workspace_path)
    except _AbortError:
        return 1

    name = args.name

    try:
        config = load_config(target_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    if name not in config.providers:
        print(f"[{STATUS_ERROR}] Provider {name!r} 不存在于 {target_path}")
        return 1

    print_banner("删除 Provider")
    print()
    print(f"目标文件：{target_path}")
    print(f"Provider：{name}")
    if config.default == name:
        print(f"  [{STATUS_WARN}] 警告：{name} 是当前默认 Provider，删除后该层无默认")

    if not args.yes and not _confirm_remove():
        print_user_aborted("删除 Provider")
        return 1

    new_config = remove_provider_from_config(config, name)
    save_config(target_path, new_config)
    print_provider_removed(name, target_path, was_default=config.default == name)
    warn_unused_after_remove(workspace_path, name)
    return 0


def _confirm_remove() -> bool:
    """删除前确认交互。"""
    while True:
        try:
            ans = input("确认删除？[y/N]: ").strip().lower()
        except EOFError:
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False
        print("请输入 y 或 n")


# ==================================================================
# yzrws model provider set-default
# ==================================================================


def run_set_default(args: argparse.Namespace) -> int:
    """实现 `yzrws model provider set-default <name>`."""
    workspace_path = paths.get_workspace_path()
    try:
        target_path = _resolve_provider_path(workspace_path)
    except _AbortError:
        return 1

    name = args.name

    try:
        config = load_config(target_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    if name not in config.providers:
        print(f"[{STATUS_ERROR}] Provider {name!r} 不存在于 {target_path}")
        print("提示：执行 yzrws model provider list 查看已有 Provider")
        return 1

    new_config = set_default_in_config(config, name)
    save_config(target_path, new_config)
    print(f"已将默认 Provider 切换为：{name}")
    return 0


# ==================================================================
# 列宽计算（与 list 表格配合）
# ==================================================================


_MIN_LIST_COL_WIDTHS = {
    "name": 4,
    "base_url": 8,
    "model": 5,
    "agent_types": 12,
}


def _compute_list_col_widths(config, engines: list[str]) -> dict[str, int]:
    """根据实际数据动态计算 list 表格的列宽。"""
    from yzrws.provider import ProviderConfig

    assert isinstance(config, ProviderConfig)
    widths = dict(_MIN_LIST_COL_WIDTHS)
    for p in config.providers.values():
        widths["name"] = max(widths["name"], len(p.name))
        widths["base_url"] = max(widths["base_url"], len(p.base_url))
        widths["model"] = max(widths["model"], len(p.model))
        agent_types = p.resolved_agent_types(engines)
        agent_types_display = (
            "all" if set(agent_types) >= set(engines) else ", ".join(agent_types)
        )
        widths["agent_types"] = max(widths["agent_types"], len(agent_types_display))
    return widths


# ==================================================================
# Provider 引用扫描（删除时给出警告）
# ==================================================================


def find_workitems_referencing_provider(
    workspace_path: Path, provider_name: str
) -> list[str]:
    """扫描 workspace 下所有工作项，列出 setting.json 中 provider == provider_name 的工作项名称。

    用于删除前的警告提示。不影响命令成功与否。
    """
    referenced: list[str] = []
    if not workspace_path.is_dir():
        return referenced

    for entry in sorted(workspace_path.iterdir()):
        if not entry.is_dir():
            continue
        setting = entry / "setting.json"
        if not setting.is_file():
            continue
        try:
            data = json.loads(setting.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("provider") == provider_name:
            referenced.append(entry.name)
    return referenced


def warn_unused_after_remove(workspace_path: Path, removed_name: str) -> None:
    """删除 Provider 后，扫描被引用工作项并打印警告。"""
    referenced = find_workitems_referencing_provider(workspace_path, removed_name)
    print_unused_provider_warning(referenced, removed_name)
