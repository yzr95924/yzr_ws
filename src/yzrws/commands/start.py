"""yzrws start 命令实现：打开工作项并启动 Agent 会话。

设计参考 doc/multi_agent_design.md 和 doc/session_design.md。
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
from yzrws.commands._name import is_valid_workitem_name
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
    archive_session,
    find_latest_session_for_engine,
    read_session,
    write_session,
)

# 顶层 --help 显示的简短描述（cli.py 的 _command_help 读取此属性）
HELP = "打开工作项并启动 Agent 会话"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws start <name>`，返回进程退出码。

    流程：
      1. 前置检查（workspace 初始化 / 名称合法性）
      2. 如果 workitem 不存在 → 自动创建
      3. 读取 setting.json 确定引擎
      4. 读取 session.json 检查当前 session
      5. 处理引擎切换（自动归档旧 session）
      6. 启动引擎进程：session 存在则自动恢复，不存在则新建（无需 --new flag）
      7. 进程退出后更新 session.json
    """
    # 解析子命令参数
    parser = argparse.ArgumentParser(
        prog="yzrws start",
        description=HELP,
        add_help=False,
    )
    parser.add_argument("name", help="工作项名称")
    parser.add_argument("--engine", "-e", help="指定引擎（创建或切换时使用）")

    # 处理 --help
    argv = args.subcmd_argv
    if argv and argv[0] in ("-h", "--help"):
        print("用法: yzrws start <name> [--engine <engine>]")
        print()
        print(HELP)
        print()
        print("如果工作项不存在，自动创建；如果已存在，根据 session 信息自动恢复会话。")
        return 0

    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        # argparse 在缺少必需参数时会调用 sys.exit(2)
        # 我们需要捕获并返回退出码
        return 2

    workspace_path = paths.get_workspace_path()
    name = parsed.name
    cli_engine = parsed.engine

    # 1. 前置检查
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    if not is_valid_workitem_name(name):
        print_workitem_name_invalid(name)
        return 1

    target = workspace_path / name

    # 2. 如果 workitem 不存在 → 自动创建
    exists_result = check_path_exists(target, name, workspace_path)
    if exists_result == "file":
        print(f"[{STATUS_ERROR}] 路径已被文件占用：{target}")
        return 1

    if exists_result is None:
        # workitem 不存在，自动创建
        if not _create_workitem(workspace_path, name, cli_engine):
            return 1

    # 3. 读取 setting.json 确定引擎
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

    # 如果 --engine 参数与 setting.json 不同，更新 setting.json
    if cli_engine and cli_engine != engine_name:
        setting["engine"] = cli_engine
        engine_name = cli_engine
        from yzrws.workspace import atomic_write_json

        atomic_write_json(setting_path, setting)
        print(f"引擎已切换为：{engine_name}")

    # 3.5 解析 workitem 生效的模型配置（按 provider_design.md §回退链）
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

    # 兼容性检查：engine_name 不在 provider.agent_types 时仅警告（不阻止；用户
    # 可能通过 --engine 临时切换）。来源为"none"（引擎内置默认）时不检查。
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

    # 3.6 解析 Outline MCP 配置（按 outline_wiki_design.md §解析逻辑）
    mcp_config = resolve_mcp_config(setting, workspace_path)
    outline_read_only = bool(setting.get("outline_read_only", False))

    # 4. 获取引擎适配器
    try:
        engine = get_engine(engine_name)
    except ValueError as e:
        print(f"[{STATUS_ERROR}] {e}")
        return 1

    # 检查引擎是否可用
    if not engine.is_available():
        print(f"[{STATUS_ERROR}] 引擎 {engine_name} 不可用")
        print(f"请确保 {engine._get_command()} 命令已安装并在 PATH 中")
        return 1

    # 5. 读取 session.json 检查当前 session
    current_session = read_session(target)

    # 6. 处理引擎切换
    if current_session and current_session.engine != engine_name:
        print(f"检测到引擎切换：{current_session.engine} → {engine_name}")
        archive_path = archive_session(target, current_session)
        print(f"已归档旧 session 到：{archive_path.relative_to(workspace_path)}")
        # 清理旧引擎的 MCP 桥接文件
        try:
            old_engine = get_engine(current_session.engine)
            old_engine.sync_mcp(target, None)
        except ValueError:
            pass  # 旧引擎不可用，跳过清理
        current_session = None

    # 7. 确定是否恢复会话：自动决策，无需 flag
    #    - session 存在且仍有效 → 恢复
    #    - session 不存在 / 失效 / 当前无 session → 启动新会话
    session_to_resume: SessionInfo | None = None

    if current_session and current_session.session_id:
        # 验证 session 是否存在
        if engine.validate_session(current_session.session_id):
            session_to_resume = current_session
        else:
            print(f"警告：记录的 session {current_session.session_id} 已不存在")
    elif current_session is None:
        # 检查是否有历史 session（引擎切换场景）
        history = find_latest_session_for_engine(target, engine_name)
        if history and history.session_id:
            if engine.validate_session(history.session_id):
                session_to_resume = history
                print(f"发现历史 {engine_name} 会话：{history.session_id}")

    # 7.5 同步 MCP 配置到引擎原生位置（含 read-only 权限管理）
    engine.sync_mcp(target, mcp_config, read_only=outline_read_only)

    # 8. 启动引擎
    print_banner("启动会话")
    print()
    print(f"工作项：{name}")
    print(f"路径：{target}")
    print(f"引擎：{engine_name}")
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
        # 会话结束后提取 session_id
        session_id = engine.extract_session_id(target)

    # 9. 更新 session.json
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if session_to_resume:
        # 恢复会话：更新 resume_count 和 updated_at
        # 同时刷新 model / provider（用户可能在 workitem 上换过绑定）
        session_to_resume.status = "paused"
        session_to_resume.updated_at = now
        session_to_resume.resume_count += 1
        session_to_resume.model = resolved_model.model
        session_to_resume.provider = resolved_model.provider_name
        write_session(target, session_to_resume)
    else:
        # 新会话：创建 session.json
        new_session = SessionInfo(
            engine=engine_name,
            session_id=session_id or "",
            status="paused",
            created_at=now,
            updated_at=now,
            resume_count=0,
            model=resolved_model.model,
            provider=resolved_model.provider_name,
        )
        write_session(target, new_session)

    # 10. 输出结果
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

    # 打印报告头部
    print_create_report_header(name, workspace_path, resolved_engine)

    # 创建目录结构
    created_items = create_directories(target, name)

    # 写入初始文件
    file_items = write_initial_files(target, name, resolved_engine)
    created_items.extend(file_items)

    # 更新 metadata
    count_before, count_after = update_metadata(workspace_path, name)
    print_metadata_update(count_before, count_after)

    # 打印创建清单
    for action, item in created_items:
        print_create_item(action, item)

    print_create_footer(name)
    print()
    print("创建工作项完成，继续启动会话...")
    print()

    return True


# 注册到子命令表
REGISTRY["start"] = run
