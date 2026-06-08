"""yzrws start 命令实现：打开工作项并启动 Agent 会话。

设计参考 doc/multi_agent_design.md 和 doc/session_design.md。

yzrws start 支持多 session：每个 workitem 下的 ``sessions/<name>.json`` 是
一份 session 元数据，``session.json`` 是 ``{"current": "<name>"}`` 指针。

场景分支：

  - current 为空 + 无 --session：创建 ``default``（title 缺省）
  - current = "x" + 无 --session：续命 x
  - --session "y"（与 current 不同）：切 current → y；y 存在则续命，不存在则创建
  - --session "y" + --engine 与 y.engine 不一致：error（避免归档 X 的歧义）
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

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
    print_banner,
    print_create_footer,
    print_create_item,
    print_create_report_header,
    print_metadata_update,
    print_session_engine_mismatch,
    print_workspace_not_initialized,
    print_workitem_name_invalid,
)
from yzrws.outline import resolve_mcp_config
from yzrws.provider import (
    ProviderConfigError,
    get_workspace_provider_path,
    load_config as load_provider_config,
    resolve_model_config,
)
from yzrws.session import (
    SessionInfo,
    find_latest_session_for_engine,
    get_current_session_name,
    migrate_legacy_session,
    read_session_by_name,
    set_current_session_name,
    write_session,
)

# 顶层 --help 显示的简短描述（cli.py 的 _command_help 读取此属性）
HELP = "打开工作项并启动 Agent 会话"


def run(args: argparse.Namespace) -> int:
    """执行 ``yzrws start <name>``，返回进程退出码。"""
    # 解析子命令参数
    parser = argparse.ArgumentParser(
        prog="yzrws start",
        description=HELP,
        add_help=False,
    )
    parser.add_argument("name", help="工作项名称")
    parser.add_argument("--engine", "-e", help="指定引擎（创建或切换时使用）")
    parser.add_argument(
        "--session",
        "-s",
        default=None,
        help="指定要恢复/创建的 session 名（缺省 = current 指针或 'default'）",
    )
    parser.add_argument(
        "--title",
        "-t",
        default=None,
        help="新建 session 时设置 title；已存在 session 忽略",
    )

    argv = args.subcmd_argv
    if argv and argv[0] in ("-h", "--help"):
        print(
            "用法: yzrws start <name> [--engine <engine>] "
            '[--session <name>] [--title "<text>"]'
        )
        print()
        print(HELP)
        print()
        print("如果工作项不存在，自动创建；")
        print("存在时按 --session / current 指针决定续命或新建。")
        return 0

    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        return 2

    workspace_path = paths.get_workspace_path()
    name = parsed.name
    cli_engine = parsed.engine
    cli_session_name = parsed.session
    cli_title = parsed.title

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
        if not _create_workitem(workspace_path, name, cli_engine):
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
        from yzrws.workspace import atomic_write_json

        atomic_write_json(setting_path, setting)
        print(f"引擎已切换为：{engine_name}")

    # 3.5 解析生效的模型配置
    try:
        provider_config = load_provider_config(
            get_workspace_provider_path(workspace_path)
        )
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
            f"  提示：执行 yzrws start {name} --engine <compatible-engine>"
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
    session_to_resume: SessionInfo | None = None
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


def _create_workitem(
    workspace_path: Path,
    name: str,
    engine: str | None,
) -> bool:
    """自动创建工作项（yzrws start 在 workitem 不存在时调用）。

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


# 注册到子命令表
REGISTRY["start"] = run
