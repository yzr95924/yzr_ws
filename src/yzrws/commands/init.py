"""yzrws init 命令实现：初始化 workspace 目录结构与自检。

设计参考 doc/workspace_init_design.md。
"""

import argparse

from yzrws import paths, workspace
from yzrws.commands import REGISTRY
from yzrws.output import (
    STATUS_ERROR,
    print_banner,
    print_failure,
    print_init_footer,
    print_items,
)
from yzrws.workspace import InitFatalError

# 顶层 --help 显示的简短描述（cli.py 的 _command_help 读取此属性）
HELP = "初始化 workspace 目录结构"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws init`，返回进程退出码（0 = 成功，1 = 失败）。

    行为对齐设计文档第 232-278 行的样例输出：
      - 成功 / 部分补全 → banner + 路径 + 6 项清单 + 底部状态
      - 致命错误（路径被文件占用 / 无写权限）→ banner + 路径 + 错误行
    """
    # 处理 --help
    if args.subcmd_argv and args.subcmd_argv[0] in ("-h", "--help"):
        print("用法: yzrws init")
        print()
        print(HELP)
        print()
        print("在 ~/yzr_workspace 创建 workspace 目录结构。")
        print("支持多次执行：已存在的项目不覆盖，缺失的项目自动补全。")
        return 0

    workspace_path = paths.get_workspace_path()
    print_banner("Workspace 初始化")
    print(f"路径：{workspace_path}")
    print()
    try:
        items = workspace.init(workspace_path)
    except InitFatalError as e:
        print_failure(e.message, e.hint)
        return 1

    print_items(items)
    print()
    has_error = any(item.status == STATUS_ERROR for item in items)
    print_init_footer(has_error)
    return 1 if has_error else 0


# 注册到子命令表
REGISTRY["init"] = run
