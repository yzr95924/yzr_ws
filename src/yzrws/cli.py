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

    使用 add_help=False 避免顶层 -h 拦截子命令的 --help 请求；
    顶层帮助由 main() 手动处理。
    """
    parser = argparse.ArgumentParser(
        prog="yzrws",
        description="yzrws — Code Agent 工作项管理器",
        add_help=False,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="子命令",
        metavar="<command>",
    )

    for name in sorted(REGISTRY.keys()):
        subparsers.add_parser(name, help=_command_help(name), add_help=False)

    return parser


def _command_help(name: str) -> str:
    """从命令模块的 HELP 属性或 docstring 第一段提取简短 help。"""
    handler = REGISTRY.get(name)
    if handler is None:
        return ""
    module = sys.modules.get(handler.__module__)
    if module is not None and hasattr(module, "HELP"):
        return module.HELP
    if handler.__doc__ is None:
        return ""
    return handler.__doc__.strip().splitlines()[0]


def _needs_help(argv: Sequence[str] | None) -> bool:
    """判断原始参数是否请求顶层帮助（无命令名 + -h/--help）。"""
    if argv is None:
        argv = sys.argv[1:]
    return bool(argv) and argv[0] in ("-h", "--help")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口：parse → dispatch → 返回退出码。

    使用 parse_known_args 而非 parse_args，以便子命令（如 workitem create）
    可以有自己的参数和嵌套子命令——顶层只识别 command 名称，
    其余参数通过 args.subcmd_argv 传递给具体命令处理器。

    Args:
        argv: 显式参数列表（None 时使用 sys.argv[1:]），便于测试。
    """
    parser = build_parser()

    # 顶层帮助：add_help=False 后需手动处理
    if _needs_help(argv):
        parser.print_help()
        return 0

    args, remainder = parser.parse_known_args(argv)

    # 将未识别的参数存到 args 上，供有子命令的处理器（如 create）使用
    args.subcmd_argv = remainder

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
