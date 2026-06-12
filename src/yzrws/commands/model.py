"""yzrws model 命令：模型 / Provider 相关的子命令组。

子命令：
  - model provider add            添加一个 Provider
  - model provider list           列出已配置 Provider
  - model provider remove <name>  删除 Provider
  - model provider set-default <name>  切换默认 Provider

设计参考 doc/provider_design.md 与 doc/command_design.md。

所有 Provider 配置统一存放在 workspace 下的 .config/provider.json。
"""

import argparse

from yzrws.commands import REGISTRY
from yzrws.commands.provider import (
    run_add,
    run_list,
    run_remove,
    run_set_default,
)

# 顶层 --help 显示的简短描述
HELP = "管理模型与 Provider 配置"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws model <subcmd> [args]`。

    model 是子命令组，包含 provider 等子命令。无参数时打印帮助并返回 1。
    """
    parser = _build_parser()
    argv = args.subcmd_argv

    # model 级帮助：add_help=False 后需手动处理
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
    """构造 model 子命令组的 ArgumentParser。"""
    parser = argparse.ArgumentParser(
        prog="yzrws model",
        description="管理模型与 Provider 配置",
        add_help=False,
    )
    subparsers = parser.add_subparsers(
        dest="subcmd",
        title="子命令",
        metavar="<subcmd>",
    )

    # ---- model provider ----
    provider_parser = subparsers.add_parser(
        "provider",
        help="管理模型 Provider（连接信息、默认 Provider 等）",
    )
    provider_sub = provider_parser.add_subparsers(
        dest="provider_cmd",
        title="Provider 子命令",
        metavar="<subcmd>",
    )

    # model provider add
    add_p = provider_sub.add_parser(
        "add",
        help="添加一个 Provider（写入 workspace 下的 .config/provider.json）",
    )
    add_p.add_argument("--name", help="Provider 名称（可省略以进入交互式输入）")
    add_p.add_argument("--base-url", help="API 端点 URL")
    add_p.add_argument(
        "--auth-key",
        help="认证密钥（CLI 传值时不隐藏回显；交互式输入默认隐藏）",
    )
    add_p.add_argument("--model", help="默认模型名称")
    add_p.add_argument(
        "--agent-type",
        dest="agent_types",
        action="append",
        help=(
            "该 provider 兼容的 engine 类型（可多次指定，如 "
            "--agent-type claude-code --agent-type opencode）；"
            "特殊值 'all' 表示兼容所有 engine（与不传此参数等价）；"
            "'all' 不能与具体 engine 混用"
        ),
    )
    add_p.add_argument(
        "--set-default",
        action="store_true",
        help="强制将新 Provider 设为默认",
    )
    add_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="同名 Provider 存在时跳过确认直接覆盖",
    )
    add_p.set_defaults(func=run_add)

    # model provider list
    list_p = provider_sub.add_parser(
        "list",
        help="列出所有已配置的 Provider",
    )
    list_p.set_defaults(func=run_list)

    # model provider remove
    rm_p = provider_sub.add_parser(
        "remove",
        help="删除一个 Provider",
    )
    rm_p.add_argument("name", help="Provider 名称")
    rm_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="跳过确认直接删除",
    )
    rm_p.set_defaults(func=run_remove)

    # model provider set-default
    sd_p = provider_sub.add_parser(
        "set-default",
        help="切换默认 Provider",
    )
    sd_p.add_argument("name", help="Provider 名称")
    sd_p.set_defaults(func=run_set_default)

    return parser


# 注册到顶层子命令表
REGISTRY["model"] = run
