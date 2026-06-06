"""yzrws CLI 入口：argparse 解析 + 子命令 dispatch。

调用方：
  - bin/yzrws（带 shebang 的入口脚本）
  - python -m yzrws（通过 __main__.py）

子命令通过 yzrws.commands.REGISTRY 注册，调用方无需在此处硬编码命令名。
"""

import argparse
import sys
from typing import Sequence

from yzrws.commands import REGISTRY


def build_parser() -> argparse.ArgumentParser:
    """构造顶层 ArgumentParser，注册所有子命令。

    子命令的 help 文本由各命令模块提供（通过 registry 的 docstring
    或显式 add_help）。当前 init 不需要参数，留空。
    """
    parser = argparse.ArgumentParser(
        prog="yzrws",
        description="yzrws — Code Agent 工作项管理器",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="子命令",
        metavar="<command>",
    )

    for name in sorted(REGISTRY.keys()):
        subparsers.add_parser(name, help=_command_help(name))

    return parser


def _command_help(name: str) -> str:
    """从命令模块的 docstring 第一段提取简短 help。"""
    handler = REGISTRY.get(name)
    if handler is None or handler.__doc__ is None:
        return ""
    first_line = handler.__doc__.strip().splitlines()[0]
    return first_line


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口：parse → dispatch → 返回退出码。

    Args:
        argv: 显式参数列表（None 时使用 sys.argv[1:]），便于测试。
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    handler = REGISTRY.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
