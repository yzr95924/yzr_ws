"""yzrws create 命令：创建资源。

子命令：
  - create workitem <name>  创建一个新的工作项

设计参考 doc/workitem_create_design.md。
创建流程的 helper（名称校验 / 目录 / 文件 / 元数据）统一在 _name /
_create_workitem / _workspace_check 模块中，create 与 start 共享。
"""

import argparse
import shutil
import subprocess

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
from yzrws.output import (
    STATUS_ERROR,
    print_create_footer,
    print_create_item,
    print_create_report_header,
    print_metadata_update,
    print_workspace_not_initialized,
    print_workitem_exists,
    print_workitem_name_invalid,
)

# 顶层 --help 显示的简短描述（cli.py 的 _command_help 读取此属性）
HELP = "创建工作项等资源"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws create <subcmd>`，分发到具体子命令处理器。

    create 是子命令组，包含 workitem 等子命令。
    无参数时打印帮助并返回 1。
    """
    parser = _build_parser()

    # create 级帮助：add_help=False 后需手动处理，
    # 使 --help 在 workitem 之前时能传递到 workitem 子解析器
    argv = args.subcmd_argv
    if argv and argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    parsed = parser.parse_args(argv)
    if parsed.subcmd is None:
        parser.print_help()
        return 1
    return parsed.func(parsed)


def _build_parser() -> argparse.ArgumentParser:
    """构造 create 子命令组的 ArgumentParser。"""
    parser = argparse.ArgumentParser(
        prog="yzrws create",
        description="创建资源（workitem 等）",
        add_help=False,
    )
    subparsers = parser.add_subparsers(
        dest="subcmd",
        title="子命令",
        metavar="<subcmd>",
    )

    # create workitem
    wp = subparsers.add_parser(
        "workitem",
        help="创建一个新的工作项",
    )
    wp.add_argument("name", help="工作项名称")
    wp.add_argument(
        "--engine",
        default=None,
        help="指定 Agent 引擎（覆盖全局默认值）",
    )
    wp.add_argument(
        "--start",
        action="store_true",
        help="创建完成后自动执行 yzrws start",
    )
    wp.set_defaults(func=_run_create_workitem)

    return parser


def _run_create_workitem(args: argparse.Namespace) -> int:
    """执行 `yzrws create workitem <name>` 的完整流程。

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
    """创建完成后自动执行 yzrws start <name>。

    通过 subprocess 调用 yzrws start，保持进程语义一致。
    如果 yzrws 不在 PATH 上，输出提示信息并返回 0（创建本身已成功）。
    """
    yzrws_cmd = shutil.which("yzrws")
    if yzrws_cmd is None:
        print("注意：yzrws 未在 PATH 中找到，跳过自动启动。")
        print(f"请手动执行：yzrws start {name}")
        return 0

    result = subprocess.run(
        [yzrws_cmd, "start", name],
        check=False,
    )
    return result.returncode


# 注册到子命令表
REGISTRY["create"] = run
