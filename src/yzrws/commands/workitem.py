"""yzrws workitem 命令：workitem 级别的配置子命令组。

子命令：
  - workitem set-model <name> --provider <name>  绑定一个 workspace Provider
  - workitem unset-model <name>                  解除绑定（恢复继承）
  - workitem show <name>                         展示 workitem 完整配置与生效模型
  - workitem set-outline <name> [--read-only]    启用 Outline MCP
  - workitem unset-outline <name>                解除 Outline 引用
  - workitem unset-outline-readonly <name>       关闭 Outline 只读模式
  - workitem session <list|show|remove|use>      管理多 session

设计参考 doc/command_design.md §配置 workitem / §管理 session 与
doc/provider_design.md §回退链 / doc/session_design.md。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from yzrws import paths
from yzrws.commands import REGISTRY
from yzrws.commands._name import (
    is_valid_session_name,
    is_valid_workitem_name,
)
from yzrws.commands._workspace_check import is_workspace_initialized
from yzrws.output import (
    STATUS_ERROR,
    STATUS_WARN,
    _display_width,
    print_banner,
    print_failure,
    print_provider_incompatible_for_engine,
    print_provider_not_found_for_set_model,
    print_session_list_empty,
    print_session_list_footer,
    print_session_list_header,
    print_session_list_row,
    print_session_name_invalid,
    print_session_not_found,
    print_session_remove_confirm,
    print_session_removed,
    print_session_show,
    print_session_use_changed,
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
from yzrws.session import (
    delete_session_by_name,
    get_current_session_name,
    list_sessions,
    migrate_legacy_session,
    read_session_by_name,
    set_current_session_name,
)
from yzrws.workspace import atomic_write_json

# 顶层 --help 显示的简短描述
HELP = "管理 workitem 级别的配置（模型 / Provider 绑定 / session 等）"


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
    except SystemExit as e:
        # argparse 错误退出码：2 = 缺少必需参数 / 参数错误
        # argparse 帮助退出码：0 = 子 parser 显示 --help（SystemExit(0)）
        code = e.code
        if isinstance(code, int):
            return code
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

    # ---- workitem set-outline ----
    set_outline_p = subparsers.add_parser(
        "set-outline",
        help="为 workitem 启用 Outline MCP（引用 workspace 的 default endpoint）",
    )
    set_outline_p.add_argument("name", help="工作项名称")
    set_outline_p.add_argument(
        "--read-only",
        action="store_true",
        default=False,
        help="启用只读模式（阻止 Outline MCP 的写操作工具）",
    )
    set_outline_p.set_defaults(func=run_set_outline)

    # ---- workitem unset-outline ----
    unset_outline_p = subparsers.add_parser(
        "unset-outline",
        help="解除 workitem 的 Outline MCP 引用（同时清除只读模式）",
    )
    unset_outline_p.add_argument("name", help="工作项名称")
    unset_outline_p.set_defaults(func=run_unset_outline)

    # ---- workitem unset-outline-readonly ----
    unset_ro_p = subparsers.add_parser(
        "unset-outline-readonly",
        help="关闭 workitem 的 Outline 只读模式（保留 Outline MCP 引用）",
    )
    unset_ro_p.add_argument("name", help="工作项名称")
    unset_ro_p.set_defaults(func=run_unset_outline_readonly)

    # ---- workitem session <list|show|remove|use> ----
    session_p = subparsers.add_parser(
        "session",
        help="管理 workitem 下的多个 session（list / show / remove / use）",
    )
    session_subs = session_p.add_subparsers(
        dest="session_subcmd",
        title="子命令",
        metavar="<subcmd>",
    )
    # session 根节点（用户输入 yzrws workitem session 不带子命令）的 dispatcher
    session_p.set_defaults(func=run_session_dispatch)

    # session list <workitem>
    s_list = session_subs.add_parser("list", help="列出 workitem 下所有 session")
    s_list.add_argument("name", help="工作项名称")
    s_list.set_defaults(func=run_session_list)

    # session show <workitem> <session>
    s_show = session_subs.add_parser("show", help="显示某个 session 的详情")
    s_show.add_argument("name", help="工作项名称")
    s_show.add_argument("session", help="session 名")
    s_show.set_defaults(func=run_session_show)

    # session remove <workitem> <session> [-y]
    s_remove = session_subs.add_parser(
        "remove", help="删除 session（仅 yzrws 元数据，不碰引擎原生数据）"
    )
    s_remove.add_argument("name", help="工作项名称")
    s_remove.add_argument("session", help="session 名")
    s_remove.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="跳过确认直接删除",
    )
    s_remove.set_defaults(func=run_session_remove)

    # session use <workitem> <session>
    s_use = session_subs.add_parser(
        "use", help="切换 workitem 的 current 指针到指定 session"
    )
    s_use.add_argument("name", help="工作项名称")
    s_use.add_argument("session", help="session 名")
    s_use.set_defaults(func=run_session_use)

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
    raw_outline = setting.get("outline")
    raw_outline_display = str(raw_outline) if raw_outline else "（未设置）"
    raw_read_only = setting.get("outline_read_only", False)
    raw_read_only_display = "true（只读）" if raw_read_only else "false（读写）"
    setting_rows: list[tuple[str, str]] = [
        ("engine", str(setting.get("engine", "—"))),
        ("model", str(setting.get("model", "—"))),
        ("provider", raw_provider_display),
        ("outline", raw_outline_display),
        ("outline_read_only", raw_read_only_display),
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


# ==================================================================
# yzrws workitem set-outline
# ==================================================================


def run_set_outline(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem set-outline <name> [--read-only]`。

    把 setting.json.outline 设为 "default"，同时按 ``--read-only``
    flag 设置 outline_read_only 字段。不读取 outline.json
    （避免在 outline.json 不存在时报错阻塞），启动时再统一解析。
    """
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

    read_only = getattr(args, "read_only", False)

    # 写入 setting.json
    setting["outline"] = "default"
    setting["outline_read_only"] = read_only
    atomic_write_json(target / "setting.json", setting)

    mode_label = "只读" if read_only else "读写"

    print_banner("设置 Workitem Outline 引用")
    print()
    print(f"工作项：{name}")
    print("引用名称：default")
    print(f"模式：{mode_label}")
    print()
    print("  [设置] setting.json.outline = 'default'")
    print(f"  [设置] setting.json.outline_read_only = {str(read_only).lower()}")
    print()
    print(f"下次 yzrws start {name} 将自动加载 Outline MCP（{mode_label}）。")
    print()
    print("=== 设置成功 ===")
    return 0


# ==================================================================
# yzrws workitem unset-outline
# ==================================================================


def run_unset_outline(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem unset-outline <name>`。

    把 outline 字段与 outline_read_only 字段从 setting.json 中移除
    （语义同 null）。
    """
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

    # 从 JSON 中移除 outline 和 outline_read_only 字段
    had_read_only = setting.pop("outline_read_only", None)
    setting.pop("outline", None)
    atomic_write_json(target / "setting.json", setting)

    print_banner("清除 Workitem Outline 引用")
    print()
    print(f"工作项：{name}")
    print()
    print("  [清除] setting.json.outline = null")
    if had_read_only:
        print("  [清除] setting.json.outline_read_only（已同步清除只读模式）")
    print()
    print(f"下次 yzrws start {name} 不再加载 Outline MCP。")
    print()
    print("=== 清除成功 ===")
    return 0


# ==================================================================
# yzrws workitem unset-outline-readonly
# ==================================================================


def run_unset_outline_readonly(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem unset-outline-readonly <name>`。

    仅清除 outline_read_only 字段，保留 outline 引用。
    """
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

    # 检查 outline 是否已启用
    outline_ref = setting.get("outline")
    if not outline_ref:
        print(
            f"[{STATUS_WARN}] workitem {name!r} 未启用 Outline MCP，只读模式无实际效果"
        )

    # 移除 outline_read_only 字段
    setting.pop("outline_read_only", None)
    atomic_write_json(target / "setting.json", setting)

    print_banner("清除 Workitem Outline 只读模式")
    print()
    print(f"工作项：{name}")
    print()
    print("  [清除] setting.json.outline_read_only = false")
    print()
    if outline_ref:
        print(
            f"Outline MCP 引用保持不变（{outline_ref!r}），"
            "下次 yzrws start 将以读写模式加载。"
        )
    print()
    print("=== 清除成功 ===")
    return 0


# ==================================================================
# yzrws workitem session <subcmd>
# ==================================================================


def _precheck_session_target(workspace_path: Path, name: str) -> Path | None:
    """session 子命令的公共前置检查 + 迁移。

    流程：workspace 初始化 → workitem 存在 → 迁移旧 session 格式 → 返回 dir。
    失败时打印错误并返回 None，caller 直接 return 1。
    """
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return None

    if not is_valid_workitem_name(name):
        print_workitem_not_found(name, workspace_path)
        return None

    target = workspace_path / name
    if not target.is_dir() or not (target / "workitem.json").is_file():
        print_workitem_not_found(name, workspace_path)
        return None

    # 旧格式迁移（幂等）
    migrate_legacy_session(target)
    return target


def run_session_dispatch(args: argparse.Namespace) -> int:
    """``yzrws workitem session`` 无子命令时的处理——打印帮助并返回 1。"""
    # 重新构造 session 子命令组的 parser 用于打印帮助
    session_parser = _build_session_parser()
    session_parser.print_help()
    return 1


def _build_session_parser() -> argparse.ArgumentParser:
    """单独构造 session 子命令组的 parser（供 dispatcher 与 bash 补全参考）。"""
    parser = argparse.ArgumentParser(
        prog="yzrws workitem session",
        description="管理 workitem 下的多个 session",
        add_help=False,
    )
    subs = parser.add_subparsers(dest="subcmd", title="子命令", metavar="<subcmd>")
    for cmd, help_text in [
        ("list", "列出 workitem 下所有 session"),
        ("show", "显示某个 session 的详情"),
        ("remove", "删除 session（仅 yzrws 元数据）"),
        ("use", "切换 workitem 的 current 指针"),
    ]:
        p = subs.add_parser(cmd, help=help_text, add_help=False)
        p.add_argument("name", help="工作项名称")
        if cmd != "list":
            p.add_argument("session", help="session 名")
        if cmd == "remove":
            p.add_argument(
                "-y",
                "--yes",
                action="store_true",
                default=False,
                help="跳过确认直接删除",
            )
    return parser


# ==================================================================
# yzrws workitem session list
# ==================================================================


def _session_list_col_widths(sessions: list) -> dict[str, int]:
    """根据实际数据动态计算列宽。"""
    titles = [s.title or "—" for s in sessions] + ["TITLE"]
    engines = [s.engine or "—" for s in sessions] + ["ENGINE"]
    names = [f"  {s.name}" for s in sessions] + ["NAME"]
    updates = ["9999-99-99 99:99:99"] + ["UPDATED"]
    return {
        "name": max(_display_width(n) for n in names),
        "title": max(_display_width(t) for t in titles),
        "engine": max(_display_width(e) for e in engines),
        "updated": max(_display_width(u) for u in updates),
    }


def run_session_list(args: argparse.Namespace) -> int:
    """实现 ``yzrws workitem session list <name>``。"""
    workspace_path = paths.get_workspace_path()
    target = _precheck_session_target(workspace_path, args.name)
    if target is None:
        return 1

    sessions = list_sessions(target)
    current = get_current_session_name(target)

    print_banner("Workitem Session 列表")
    print()
    print(f"工作项：{args.name}")
    print(f"路径：{target}")
    print()

    if not sessions:
        print_session_list_empty(current)
        return 0

    col_widths = _session_list_col_widths(sessions)
    print_session_list_header(col_widths)
    for s in sessions:
        print_session_list_row(
            name=s.name,
            title=s.title,
            engine=s.engine,
            updated_at=s.updated_at,
            is_current=(current is not None and s.name == current),
            col_widths=col_widths,
        )
    print_session_list_footer(current)
    return 0


# ==================================================================
# yzrws workitem session show
# ==================================================================


def run_session_show(args: argparse.Namespace) -> int:
    """实现 ``yzrws workitem session show <name> <session>``。"""
    workspace_path = paths.get_workspace_path()
    target = _precheck_session_target(workspace_path, args.name)
    if target is None:
        return 1

    if not is_valid_session_name(args.session):
        print_session_name_invalid(args.session)
        return 1

    info = read_session_by_name(target, args.session)
    if info is None:
        print_session_not_found(workitem_name=args.name, session_name=args.session)
        return 1

    current = get_current_session_name(target)
    print_session_show(
        workitem_name=args.name,
        session_name=info.name,
        engine=info.engine,
        session_id=info.session_id,
        status=info.status,
        title=info.title,
        model=info.model or "",
        provider=info.provider or "",
        created_at=info.created_at,
        updated_at=info.updated_at,
        resume_count=info.resume_count,
        is_current=(current is not None and info.name == current),
    )
    return 0


# ==================================================================
# yzrws workitem session remove
# ==================================================================


def run_session_remove(args: argparse.Namespace) -> int:
    """实现 ``yzrws workitem session remove <name> <session> [-y]``。"""
    workspace_path = paths.get_workspace_path()
    target = _precheck_session_target(workspace_path, args.name)
    if target is None:
        return 1

    if not is_valid_session_name(args.session):
        print_session_name_invalid(args.session)
        return 1

    info = read_session_by_name(target, args.session)
    if info is None:
        print_session_not_found(workitem_name=args.name, session_name=args.session)
        return 1

    current = get_current_session_name(target)
    is_current = current is not None and info.name == current

    # 确认
    if not args.yes:
        print_banner("删除 Session")
        print()
        print(f"工作项：{args.name}")
        print(f"Session：{info.name}")
        print()
        if not print_session_remove_confirm(
            workitem_name=args.name,
            session_name=info.name,
            is_current=is_current,
        ):
            print()
            print("删除已取消。")
            return 0

    # 真删
    delete_session_by_name(target, info.name)
    if is_current:
        set_current_session_name(target, None)

    print_session_removed(
        workitem_name=args.name,
        session_name=info.name,
        was_current=is_current,
    )
    return 0


# ==================================================================
# yzrws workitem session use
# ==================================================================


def run_session_use(args: argparse.Namespace) -> int:
    """实现 ``yzrws workitem session use <name> <session>``。"""
    workspace_path = paths.get_workspace_path()
    target = _precheck_session_target(workspace_path, args.name)
    if target is None:
        return 1

    if not is_valid_session_name(args.session):
        print_session_name_invalid(args.session)
        return 1

    info = read_session_by_name(target, args.session)
    if info is None:
        print_session_not_found(workitem_name=args.name, session_name=args.session)
        return 1

    old = get_current_session_name(target)
    set_current_session_name(target, info.name)
    print_session_use_changed(
        workitem_name=args.name,
        old=old,
        new=info.name,
    )
    return 0


# 注册到顶层子命令表
REGISTRY["workitem"] = run
