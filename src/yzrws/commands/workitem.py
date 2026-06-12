"""yzrws workitem 命令：workitem 级别的配置子命令组。

子命令：
  - workitem create <name> [--engine <engine>] [--start]
                                                  创建一个新的工作项
  - workitem start <name> [--engine <engine>] [--session <name>] [--title "<text>"]
                                                  打开工作项并启动 Agent 会话
  - workitem set-model <name> --provider <name>  绑定一个 workspace Provider
  - workitem unset-model <name>                  解除绑定（恢复继承）
  - workitem show <name>                         展示 workitem 完整配置与生效模型
  - workitem set-outline <name> [--read-only]    启用 Outline MCP
  - workitem unset-outline <name>                解除 Outline 引用
  - workitem unset-outline-readonly <name>       关闭 Outline 只读模式
  - workitem session <list|show|remove|use>      管理多 session

设计参考 doc/command_design.md §配置 workitem / §管理 session / §打开 workitem
与 doc/provider_design.md §回退链 / doc/session_design.md /
doc/workitem_create_design.md。
"""

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from yzrws import paths
from yzrws.commands import REGISTRY
from yzrws.commands._create_workitem import (
    check_path_exists,
    create_directories,
    resolve_engine,
    update_metadata,
    write_initial_files,
)
from yzrws.commands._name import (
    is_valid_session_name,
    is_valid_workitem_name,
)
from yzrws.commands._workspace_check import is_workspace_initialized
from yzrws.engine import get_engine
from yzrws.output import (
    STATUS_ERROR,
    STATUS_WARN,
    _display_width,
    print_banner,
    print_create_footer,
    print_create_item,
    print_create_report_header,
    print_failure,
    print_metadata_update,
    print_provider_incompatible_for_engine,
    print_provider_not_found_for_set_model,
    print_session_engine_mismatch,
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
    print_workitem_exists,
    print_workitem_name_invalid,
    print_workitem_not_found,
    print_workitem_set_model,
    print_workitem_show_header,
    print_workitem_show_section,
    print_workitem_unset_model,
)
from yzrws.outline import resolve_mcp_config
from yzrws.provider import (
    ProviderConfigError,
    get_workspace_provider_path,
    load_config,
    resolve_model_config,
)
from yzrws.session import (
    SessionInfo,
    delete_session_by_name,
    find_latest_session_for_engine,
    get_current_session_name,
    list_sessions,
    migrate_legacy_session,
    read_session_by_name,
    set_current_session_name,
    write_session,
)
from yzrws.workspace import atomic_write_json

# 顶层 --help 显示的简短描述
HELP = "管理 workitem（创建 / 模型 / Provider 绑定 / session 等）"


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

    # ---- workitem create ----
    create_p = subparsers.add_parser(
        "create",
        help="创建一个新的工作项",
    )
    create_p.add_argument("name", help="工作项名称")
    create_p.add_argument(
        "--engine",
        default=None,
        help="指定 Agent 引擎（覆盖全局默认值）",
    )
    create_p.add_argument(
        "--start",
        action="store_true",
        help="创建完成后自动执行 yzrws workitem start",
    )
    create_p.set_defaults(func=run_create)

    # ---- workitem start ----
    start_p = subparsers.add_parser(
        "start",
        help="打开工作项并启动 Agent 会话",
    )
    start_p.add_argument("name", help="工作项名称")
    start_p.add_argument(
        "--engine",
        "-e",
        default=None,
        help="指定引擎（创建或切换时使用）",
    )
    start_p.add_argument(
        "--session",
        "-s",
        default=None,
        help="指定要恢复/创建的 session 名（缺省 = current 指针或 'default'）",
    )
    start_p.add_argument(
        "--title",
        "-t",
        default=None,
        help="新建 session 时设置 title；已存在 session 忽略",
    )
    start_p.set_defaults(func=run_start)

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


def _resolve_workitem_dir(workspace_path: Path, name: str) -> Optional[Path]:
    """检查 workitem 存在性，返回其目录；不存在返回 None。"""
    if not is_valid_workitem_name(name):
        return None
    target = workspace_path / name
    if not target.is_dir() or not (target / "workitem.json").is_file():
        return None
    return target


def _read_setting(target: Path) -> Optional[Dict]:
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
# yzrws workitem create
# ==================================================================


def run_create(args: argparse.Namespace) -> int:
    """实现 `yzrws workitem create <name> [--engine <engine>] [--start]`。

    流程（对齐 doc/workitem_create_design.md §创建流程）：
      1. 前置检查（workspace 初始化 / 名称合法性 / 路径冲突）
      2. 创建目录结构
      3. 写入初始文件（workitem.json / setting.json / CLAUDE.md）
      4. 更新 workspace 级 metadata.json
      5. 输出创建报告
      6. 可选串联启动（--start）
    """
    workspace_path = paths.get_workspace_path()
    name = args.name

    # 1. 前置检查
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    if not is_valid_workitem_name(name):
        print_workitem_name_invalid(name)
        return 1

    target = workspace_path / name
    exists_result = check_path_exists(target, name, workspace_path)
    if exists_result is not None:
        # 目录已存在 → 幂等回显；文件已存在 → 报错
        if exists_result == "directory":
            print_workitem_exists(name, workspace_path)
            return 0
        # 同名文件占用
        print(f"[{STATUS_ERROR}] 路径已被文件占用：{target}")
        return 1

    # 解析引擎
    engine = resolve_engine(args.engine)

    # 打印报告头部
    print_create_report_header(name, workspace_path, engine)

    # 2. 创建目录结构
    created_items = create_directories(target, name)

    # 3. 写入初始文件
    file_items = write_initial_files(target, name, engine)
    created_items.extend(file_items)

    # 4. 更新 workspace 元数据
    count_before, count_after = update_metadata(workspace_path, name)

    # 5. 打印创建清单（目录和文件在前，元数据更新在后）
    for action, item in created_items:
        print_create_item(action, item)
    print_metadata_update(count_before, count_after)

    # 打印底部成功信息
    print_create_footer(name)

    # 6. 可选：串联启动
    if args.start:
        return _auto_start(name)

    return 0


def _auto_start(name: str) -> int:
    """创建完成后自动执行 yzrws workitem start <name>。

    通过 subprocess 调用 yzrws workitem start，保持进程语义一致。
    如果 yzrws 不在 PATH 上，输出提示信息并返回 0（创建本身已成功）。
    """
    yzrws_cmd = shutil.which("yzrws")
    if yzrws_cmd is None:
        print("注意：yzrws 未在 PATH 中找到，跳过自动启动。")
        print(f"请手动执行：yzrws workitem start {name}")
        return 0

    result = subprocess.run(
        [yzrws_cmd, "workitem", "start", name],
        check=False,
    )
    return result.returncode


# ==================================================================
# yzrws workitem start
# ==================================================================


def run_start(args: argparse.Namespace) -> int:
    """实现 ``yzrws workitem start <name>``，返回进程退出码。

    场景分支（对齐 doc/session_design.md §Session 生命周期）：

      - current 为空 + 无 --session：创建 ``default``（title 缺省）
      - current = "x" + 无 --session：续命 x
      - --session "y"（与 current 不同）：切 current → y；y 存在则续命，不存在则创建
      - --session "y" + --engine 与 y.engine 不一致：error（避免归档 X 的歧义）
    """
    name = args.name
    cli_engine = args.engine
    cli_session_name = args.session
    cli_title = args.title

    workspace_path = paths.get_workspace_path()

    # 1. 前置检查
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    if not is_valid_workitem_name(name):
        print_workitem_name_invalid(name)
        return 1

    target = workspace_path / name

    # 2. workitem 不存在 → 自动创建
    exists_result = check_path_exists(target, name, workspace_path)
    if exists_result == "file":
        print(f"[{STATUS_ERROR}] 路径已被文件占用：{target}")
        return 1

    if exists_result is None:
        if not _auto_create_workitem(workspace_path, name, cli_engine):
            return 1

    # 3. 读 setting.json
    setting_path = target / "setting.json"
    if not setting_path.is_file():
        print(f"[{STATUS_ERROR}] 缺少 setting.json：{setting_path}")
        return 1

    try:
        setting = json.loads(setting_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[{STATUS_ERROR}] 读取 setting.json 失败：{e}")
        return 1

    engine_name = setting.get("engine", "claude-code")

    # --engine 切换
    if cli_engine and cli_engine != engine_name:
        setting["engine"] = cli_engine
        engine_name = cli_engine
        atomic_write_json(setting_path, setting)
        print(f"引擎已切换为：{engine_name}")

    # 3.5 解析生效的模型配置
    try:
        provider_config = load_config(get_workspace_provider_path(workspace_path))
    except ProviderConfigError as e:
        print(f"[{STATUS_ERROR}] 读取 provider.json 失败：{e}")
        return 1
    from yzrws.engine import list_engines

    try:
        resolved_model = resolve_model_config(setting, provider_config, list_engines())
    except KeyError as e:
        print(
            f"[{STATUS_ERROR}] workitem 引用了不存在的 Provider {e.args[0]!r}；"
            "请执行 yzrws workitem unset-model 或 yzrws workitem set-model 重设"
        )
        return 1

    if (
        resolved_model.source != "none"
        and resolved_model.agent_types
        and engine_name not in resolved_model.agent_types
    ):
        compatible = ", ".join(resolved_model.agent_types)
        print(
            f"[{STATUS_WARN}] 当前 engine {engine_name!r} 与"
            f" provider {resolved_model.provider_name!r} 不兼容："
            f"该 provider 仅支持 {compatible}"
        )
        print(
            f"  提示：执行 yzrws workitem start {name} --engine <compatible-engine>"
            " 切换到兼容的 engine，或 yzrws workitem unset-model 解除绑定"
        )
        print()

    # 3.6 解析 Outline MCP 配置
    mcp_config = resolve_mcp_config(setting, workspace_path)
    outline_read_only = bool(setting.get("outline_read_only", False))

    # 4. 引擎就绪检查
    try:
        engine = get_engine(engine_name)
    except ValueError as e:
        print(f"[{STATUS_ERROR}] {e}")
        return 1

    if not engine.is_available():
        print(f"[{STATUS_ERROR}] 引擎 {engine_name} 不可用")
        print(f"请确保 {engine._get_command()} 命令已安装并在 PATH 中")
        return 1

    # 5. ★ 多 session 决策
    # 5.1 旧格式迁移（幂等）
    migrate_legacy_session(target)

    # 5.2 决定 target session 名
    if cli_session_name is not None:
        if not is_valid_session_name(cli_session_name):
            print(f"[{STATUS_ERROR}] --session 名不合法：{cli_session_name!r}")
            print()
            print("命名规则：1-32 字符，小写字母/数字开头，可含 -_")
            return 1
        target_session_name: str = cli_session_name
    else:
        current_name = get_current_session_name(target)
        target_session_name = current_name if current_name is not None else "default"

    # 5.3 读 target session（可能不存在 = 新建场景）
    target_session = read_session_by_name(target, target_session_name)

    # 5.4 引擎冲突检测
    if target_session is not None and target_session.engine != engine_name:
        print_session_engine_mismatch(
            workitem_name=name,
            session_name=target_session.name,
            session_engine=target_session.engine,
            requested_engine=engine_name,
        )
        return 1

    # 7. 确定是否恢复会话
    session_to_resume: Optional[SessionInfo] = None
    if target_session is not None and target_session.session_id:
        if engine.validate_session(target_session.session_id):
            session_to_resume = target_session
        else:
            print(f"警告：记录的 session {target_session.session_id} 已不存在")
            target_session = None
    elif target_session is None and cli_session_name is None:
        # 用户没显式指定 session 时，尝试从归档恢复（首次自动创建时
        # 也许上一轮引擎切换留了归档）
        history = find_latest_session_for_engine(target, engine_name)
        if (
            history
            and history.session_id
            and engine.validate_session(history.session_id)
        ):
            session_to_resume = history
            print(f"发现历史 {engine_name} 会话：{history.session_id}")

    # 7.5 同步 MCP 配置
    engine.sync_mcp(target, mcp_config, read_only=outline_read_only)

    # 8. 启动引擎
    print_banner("启动会话")
    print()
    print(f"工作项：{name}")
    print(f"路径：{target}")
    print(f"引擎：{engine_name}")
    print(
        f"Session：{target_session_name}{'  [续命]' if session_to_resume else '  [新建]'}"
    )
    if resolved_model.source != "none":
        print(f"模型：{resolved_model.model}（来自 {resolved_model.provider_name}）")
    if mcp_config:
        mode = "只读" if outline_read_only else "读写"
        print(f"Outline MCP：已启用（{mode}）")
    print()

    if session_to_resume:
        print(f"恢复会话：{session_to_resume.session_id}")
        print()
        exit_code = engine.resume(
            target, session_to_resume.session_id, model=resolved_model
        )
        session_id = session_to_resume.session_id
    else:
        print("启动新会话")
        print()
        exit_code = engine.start(target, model=resolved_model)
        session_id = engine.extract_session_id(target)

    # 9. 写回 sessions/<name>.json
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if session_to_resume is not None:
        # 续命：沿用旧 created_at，刷新 status / updated_at / resume_count
        # / model / provider；name 不变。
        session_to_resume.status = "paused"
        session_to_resume.updated_at = now
        session_to_resume.resume_count += 1
        session_to_resume.model = resolved_model.model
        session_to_resume.provider = resolved_model.provider_name
        write_session(target, session_to_resume)
    else:
        # 新建
        new_session = SessionInfo(
            name=target_session_name,
            engine=engine_name,
            session_id=session_id or "",
            status="paused",
            title=(cli_title or ""),
            created_at=now,
            updated_at=now,
            resume_count=0,
            model=resolved_model.model,
            provider=resolved_model.provider_name,
        )
        write_session(target, new_session)

    # 10. 更新 current 指针
    old_current = get_current_session_name(target)
    if old_current != target_session_name:
        set_current_session_name(target, target_session_name)
        if cli_session_name is not None and old_current is not None:
            print(f"已将 current 切换为：{target_session_name}")
        elif cli_session_name is not None and old_current is None:
            print(f"已设置 current：{target_session_name}")

    # 11. 输出结果
    print()
    if exit_code == 0:
        print("会话已正常退出")
        if session_id:
            print(f"Session ID：{session_id}")
    else:
        print(f"会话异常退出（退出码：{exit_code}）")

    return exit_code


def _auto_create_workitem(
    workspace_path: Path,
    name: str,
    engine: Optional[str],
) -> bool:
    """自动创建工作项（yzrws workitem start 在 workitem 不存在时调用）。

    复用 commands/_create_workitem.py 的公共创建逻辑。

    Returns:
        True 表示创建成功，False 表示失败
    """
    target = workspace_path / name
    resolved_engine = resolve_engine(engine)

    print(f"工作项 {name} 不存在，正在创建...")
    print()

    print_create_report_header(name, workspace_path, resolved_engine)
    created_items = create_directories(target, name)
    file_items = write_initial_files(target, name, resolved_engine)
    created_items.extend(file_items)
    count_before, count_after = update_metadata(workspace_path, name)
    print_metadata_update(count_before, count_after)
    for action, item in created_items:
        print_create_item(action, item)
    print_create_footer(name)
    print()
    print("创建工作项完成，继续启动会话...")
    print()

    return True


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
    workitem_data: Dict = {}
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
    basic_rows: List[Tuple[str, str]] = [
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
    setting_rows: List[Tuple[str, str]] = [
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
    resolved_rows: List[Tuple[str, str]] = [
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
    print(f"下次 yzrws workitem start {name} 将自动加载 Outline MCP（{mode_label}）。")
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
    print(f"下次 yzrws workitem start {name} 不再加载 Outline MCP。")
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
            "下次 yzrws workitem start 将以读写模式加载。"
        )
    print()
    print("=== 清除成功 ===")
    return 0


# ==================================================================
# yzrws workitem session <subcmd>
# ==================================================================


def _precheck_session_target(workspace_path: Path, name: str) -> Optional[Path]:
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


def _session_list_col_widths(sessions: list) -> Dict[str, int]:
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
