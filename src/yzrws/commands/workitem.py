"""yzrws workitem 命令：workitem 级别的配置子命令组。

子命令：
  - workitem set-model <name> --provider <name>  绑定一个 workspace Provider
  - workitem unset-model <name>                  解除绑定（恢复继承）
  - workitem show <name>                         展示 workitem 完整配置与生效模型

设计参考 doc/command_design.md §配置 workitem 与 doc/provider_design.md §回退链。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from yzrws import paths
from yzrws.commands import REGISTRY
from yzrws.commands._name import is_valid_workitem_name
from yzrws.commands._workspace_check import is_workspace_initialized
from yzrws.output import (
    STATUS_ERROR,
    print_failure,
    print_provider_incompatible_for_engine,
    print_provider_not_found_for_set_model,
    print_workspace_not_initialized,
    print_workitem_not_found,
    print_workitem_set_model,
    print_workitem_show_header,
    print_workitem_show_section,
    print_workitem_unset_model,
)
from yzrws.provider import (
    ProviderConfigError,
    load_config,
    resolve_model_config,
)
from yzrws.workspace import atomic_write_json

# 顶层 --help 显示的简短描述
HELP = "管理 workitem 级别的配置（模型 / Provider 绑定等）"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws workitem <subcmd> [args]`。

    workitem 是子命令组，包含 set-model / unset-model / show 等子命令。
    无参数时打印帮助并返回 1。
    """
    parser = _build_parser()
    argv = args.subcmd_argv

    # workitem 级帮助：add_help=False 后需手动处理
    if argv and argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        # argparse 在缺少必需参数时调用 sys.exit(2)
        return 2

    if parsed.subcmd is None:
        parser.print_help()
        return 1
    return parsed.func(parsed)


def _build_parser() -> argparse.ArgumentParser:
    """构造 workitem 子命令组的 ArgumentParser。"""
    parser = argparse.ArgumentParser(
        prog="yzrws workitem",
        description="管理 workitem 级别的配置（模型 / Provider 绑定等）",
        add_help=False,
    )
    subparsers = parser.add_subparsers(
        dest="subcmd",
        title="子命令",
        metavar="<subcmd>",
    )

    # ---- workitem set-model ----
    set_p = subparsers.add_parser(
        "set-model",
        help="把 workitem 绑定到 workspace 中已配置的某个 Provider",
    )
    set_p.add_argument("name", help="工作项名称")
    set_p.add_argument(
        "--provider",
        required=True,
        help="Provider 名称（必须是 workspace provider.json 中已配置的）",
    )
    set_p.set_defaults(func=run_set_model)

    # ---- workitem unset-model ----
    unset_p = subparsers.add_parser(
        "unset-model",
        help="解除 workitem 的 Provider 绑定，恢复继承 workspace 默认",
    )
    unset_p.add_argument("name", help="工作项名称")
    unset_p.set_defaults(func=run_unset_model)

    # ---- workitem show ----
    show_p = subparsers.add_parser(
        "show",
        help="展示 workitem 完整配置（含生效的模型 / Provider）",
    )
    show_p.add_argument("name", help="工作项名称")
    show_p.set_defaults(func=run_show)

    return parser


# ==================================================================
# 前置检查
# ==================================================================


def _resolve_workitem_dir(workspace_path: Path, name: str) -> Path | None:
    """检查 workitem 存在性，返回其目录；不存在返回 None。"""
    if not is_valid_workitem_name(name):
        return None
    target = workspace_path / name
    if not target.is_dir() or not (target / "workitem.json").is_file():
        return None
    return target


def _read_setting(target: Path) -> dict | None:
    """读取 workitem 的 setting.json；不存在或解析失败时返回 None。"""
    setting_path = target / "setting.json"
    if not setting_path.is_file():
        return None
    try:
        data = json.loads(setting_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


# ==================================================================
# yzrws workitem set-model
# ==================================================================


def run_set_model(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem set-model <name> --provider <name>`."""
    workspace_path = paths.get_workspace_path()
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    name = args.name
    if not is_valid_workitem_name(name):
        print_workitem_not_found(name, workspace_path)
        return 1

    target = _resolve_workitem_dir(workspace_path, name)
    if target is None:
        print_workitem_not_found(name, workspace_path)
        return 1

    setting = _read_setting(target)
    if setting is None:
        print(f"[{STATUS_ERROR}] 读取 {target / 'setting.json'} 失败")
        return 1

    provider_name = args.provider

    # 校验 provider 在 workspace 中存在
    from yzrws.provider import get_workspace_provider_path

    provider_path = get_workspace_provider_path(workspace_path)
    try:
        provider_config = load_config(provider_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    if provider_name not in provider_config.providers:
        print_provider_not_found_for_set_model(provider_name, workspace_path)
        return 1

    p = provider_config.providers[provider_name]

    # 兼容性检查：provider.agent_types 不包含 workitem 当前 engine 时报错
    from yzrws.engine import list_engines

    engines = list_engines()
    agent_types = p.resolved_agent_types(engines)
    workitem_engine = str(setting.get("engine", "claude-code"))
    if workitem_engine not in agent_types:
        print_provider_incompatible_for_engine(
            provider_name=provider_name,
            workitem_name=name,
            workitem_engine=workitem_engine,
            provider_agent_types=agent_types,
        )
        return 1

    # 写入 setting.json
    setting["provider"] = provider_name
    atomic_write_json(target / "setting.json", setting)

    print_workitem_set_model(
        workitem_name=name,
        provider_name=provider_name,
        model=p.model,
        base_url=p.base_url,
        agent_types=agent_types,
    )
    return 0


# ==================================================================
# yzrws workitem unset-model
# ==================================================================


def run_unset_model(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem unset-model <name>`."""
    workspace_path = paths.get_workspace_path()
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    name = args.name
    target = _resolve_workitem_dir(workspace_path, name)
    if target is None:
        print_workitem_not_found(name, workspace_path)
        return 1

    setting = _read_setting(target)
    if setting is None:
        print(f"[{STATUS_ERROR}] 读取 {target / 'setting.json'} 失败")
        return 1

    setting["provider"] = None
    atomic_write_json(target / "setting.json", setting)

    print_workitem_unset_model(name)
    return 0


# ==================================================================
# yzrws workitem show
# ==================================================================


def run_show(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem show <name>`."""
    workspace_path = paths.get_workspace_path()
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    name = args.name
    target = _resolve_workitem_dir(workspace_path, name)
    if target is None:
        print_workitem_not_found(name, workspace_path)
        return 1

    # 读取 setting.json + workitem.json
    setting = _read_setting(target) or {}
    workitem_json = target / "workitem.json"
    workitem_data: dict = {}
    if workitem_json.is_file():
        try:
            w = json.loads(workitem_json.read_text(encoding="utf-8"))
            if isinstance(w, dict):
                workitem_data = w
        except (json.JSONDecodeError, OSError):
            pass

    # 加载 workspace provider.json（缺失时视为空）
    from yzrws.provider import get_workspace_provider_path

    provider_path = get_workspace_provider_path(workspace_path)
    try:
        provider_config = load_config(provider_path)
    except ProviderConfigError as e:
        print_failure(str(e), "请修正 provider.json 后重试")
        return 1

    # 解析生效配置（传入已注册 engine 列表，让 Provider.agent_types 缺省时回退到 all）
    from yzrws.engine import list_engines

    engines = list_engines()
    resolved = resolve_model_config(setting, provider_config, engines)

    print_workitem_show_header()

    # Section 1: 基本信息
    basic_rows: list[tuple[str, str]] = [
        ("name", name),
        ("path", str(target)),
        ("status", str(workitem_data.get("status", "—"))),
        ("created_at", str(workitem_data.get("created_at", "—"))),
    ]
    print_workitem_show_section("基本信息", basic_rows)

    # Section 2: setting.json（原始）
    raw_provider = setting.get("provider")
    raw_provider_display = str(raw_provider) if raw_provider else "（未设置）"
    setting_rows: list[tuple[str, str]] = [
        ("engine", str(setting.get("engine", "—"))),
        ("model", str(setting.get("model", "—"))),
        ("provider", raw_provider_display),
    ]
    print_workitem_show_section("setting.json（原始）", setting_rows)

    # Section 3: 生效配置（按回退链解析）
    source_label = {
        "workitem": "workitem 显式设置",
        "workspace_default": "workspace default",
        "none": "未配置（使用引擎内置默认）",
    }.get(resolved.source, resolved.source)
    agent_types_display = (
        ", ".join(resolved.agent_types) if resolved.agent_types else "—"
    )
    resolved_rows: list[tuple[str, str]] = [
        ("source", source_label),
        ("provider", str(resolved.provider_name) if resolved.provider_name else "—"),
        ("model", str(resolved.model) if resolved.model else "—"),
        ("base_url", str(resolved.base_url) if resolved.base_url else "—"),
        ("agent_types", agent_types_display),
    ]
    print_workitem_show_section("生效配置（回退链结果）", resolved_rows)

    return 0


# 注册到顶层子命令表
REGISTRY["workitem"] = run
