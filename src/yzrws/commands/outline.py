"""yzrws outline 命令：Outline Wiki MCP 配置管理。

子命令：
  - outline add     [--endpoint <url>] [--auth-token <token>] [-y]
  - outline show
  - outline update  [--endpoint <url>] [--auth-token <token>] [-y]
  - outline remove  [-y]

设计参考 doc/outline_wiki_design.md §命令集。

所有 Outline 配置存放在 workspace 下的 <workspace>/.config/outline.json。
"""

import argparse
import getpass
import sys
from typing import Optional

from yzrws import paths
from yzrws.commands import REGISTRY
from yzrws.commands._workspace_check import is_workspace_initialized
from yzrws.outline import (
    OutlineConfig,
    find_workitems_referencing_outline,
    get_workspace_outline_path,
    is_valid_endpoint,
    load_outline,
    mask_token,
    remove_outline,
    save_outline,
)
from yzrws.output import (
    STATUS_ERROR,
    STATUS_WARN,
    print_banner,
    print_user_aborted,
    print_workspace_not_initialized,
)

# 顶层 --help 显示的简短描述
HELP = "管理 Outline Wiki MCP 配置"


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws outline <subcmd> [args]`。

    outline 是子命令组，包含 add / show / update / remove 子命令。
    无参数时打印帮助并返回 1。
    """
    parser = _build_parser()
    argv = args.subcmd_argv

    # outline 级帮助
    if argv and argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        return 2

    if parsed.subcmd is None:
        parser.print_help()
        return 1
    return parsed.func(parsed)


def _build_parser() -> argparse.ArgumentParser:
    """构造 outline 子命令组的 ArgumentParser。"""
    parser = argparse.ArgumentParser(
        prog="yzrws outline",
        description=HELP,
        add_help=False,
    )
    subparsers = parser.add_subparsers(
        dest="subcmd",
        title="子命令",
        metavar="<subcmd>",
    )

    # ---- outline add ----
    add_p = subparsers.add_parser(
        "add",
        help="添加 Outline Wiki 连接配置",
    )
    add_p.add_argument(
        "--endpoint", help="Outline 实例 URL（如 https://my-team.getoutline.com）"
    )
    add_p.add_argument("--auth-token", help="Outline API key")
    add_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    add_p.set_defaults(func=run_add)

    # ---- outline show ----
    show_p = subparsers.add_parser(
        "show",
        help="展示当前 Outline 配置（auth_token 脱敏）",
    )
    show_p.set_defaults(func=run_show)

    # ---- outline update ----
    update_p = subparsers.add_parser(
        "update",
        help="更新 Outline 配置的 endpoint 或 auth_token（至少一个）",
    )
    update_p.add_argument("--endpoint", help="新的 Outline 实例 URL")
    update_p.add_argument("--auth-token", help="新的 Outline API key")
    update_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    update_p.set_defaults(func=run_update)

    # ---- outline remove ----
    remove_p = subparsers.add_parser(
        "remove",
        help="删除 Outline 配置并扫描引用",
    )
    remove_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    remove_p.set_defaults(func=run_remove)

    return parser


# ==================================================================
# 前置检查
# ==================================================================


class _AbortError(Exception):
    """内部信号：用户中止或前置检查失败，要求退出当前子命令。"""


def _require_workspace(workspace_path) -> None:
    """校验 workspace 已初始化，否则打印提示并 raise _AbortError。"""
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        raise _AbortError


def _prompt_or_arg(label: str, cli_value: Optional[str], *, validator) -> str:
    """从 CLI 参数取值；为空时进入交互式输入，使用 validator 校验。"""
    if cli_value:
        value = cli_value
    else:
        try:
            value = input(f"{label}: ").strip()
        except EOFError:
            print(f"\n[{STATUS_ERROR}] 输入中断", file=sys.stderr)
            raise _AbortError from None
    if not validator(value):
        print(f"[{STATUS_ERROR}] {label} 不合法：{value!r}")
        if "URL" in label or "endpoint" in label.lower():
            print("  endpoint 必须是 HTTPS URL（如 https://my-team.getoutline.com）")
        raise _AbortError
    return value


def _prompt_secret(label: str, cli_value: Optional[str]) -> str:
    """交互式隐藏输入 API key；CLI 传值时直接使用。"""
    if cli_value:
        return cli_value
    try:
        value = getpass.getpass(f"{label}: ")
    except (EOFError, KeyboardInterrupt):
        print(f"\n[{STATUS_ERROR}] 输入中断", file=sys.stderr)
        raise _AbortError from None
    if not value:
        print(f"[{STATUS_ERROR}] {label} 不能为空")
        raise _AbortError
    return value


def _normalize_endpoint(url: str) -> str:
    """规范化 endpoint URL：去掉尾随 / 和 /mcp 路径。"""
    url = url.rstrip("/")
    if url.endswith("/mcp"):
        url = url[:-4].rstrip("/")
    return url


def _confirm(message: str) -> bool:
    """通用确认交互。"""
    while True:
        try:
            ans = input(f"{message} [y/N]: ").strip().lower()
        except EOFError:
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False
        print("请输入 y 或 n")


# ==================================================================
# yzrws outline add
# ==================================================================


def run_add(args: argparse.Namespace) -> int:
    """实现 `yzrws outline add [--endpoint ...] [--auth-token ...] [-y]`."""
    workspace_path = paths.get_workspace_path()
    try:
        _require_workspace(workspace_path)
    except _AbortError:
        return 1

    outline_path = get_workspace_outline_path(workspace_path)

    # 前置检查：配置是否已存在
    existing = load_outline(outline_path)
    if existing is not None:
        print(f"[{STATUS_ERROR}] Outline 配置已存在：{outline_path}")
        print()
        print("提示：执行 yzrws outline update 更新配置")
        return 1

    print_banner("添加 Outline 配置")
    print()
    print(f"目标文件：{outline_path}")
    print()
    print("提示：在 Outline 后台 Settings → API → Create API key 生成 API key")
    print()

    try:
        endpoint = _prompt_or_arg(
            "Outline URL",
            args.endpoint,
            validator=is_valid_endpoint,
        )
        endpoint = _normalize_endpoint(endpoint)
        auth_token = _prompt_secret("API Key", args.auth_token)
    except _AbortError:
        return 1

    config = OutlineConfig(endpoint=endpoint, auth_token=auth_token)
    save_outline(outline_path, config)

    print()
    print(f"  [新增] endpoint: {endpoint}")
    print(f"  [新增] auth_token: {mask_token(auth_token)}")
    print()
    print("=== 添加成功 ===")
    print()
    print("提示：执行 yzrws workitem set-outline <name> 为工作项启用 Outline MCP")
    return 0


# ==================================================================
# yzrws outline show
# ==================================================================


def run_show(args: argparse.Namespace) -> int:  # noqa: ARG001
    """实现 `yzrws outline show`."""
    workspace_path = paths.get_workspace_path()
    try:
        _require_workspace(workspace_path)
    except _AbortError:
        return 1

    outline_path = get_workspace_outline_path(workspace_path)
    config = load_outline(outline_path)

    if config is None:
        print("尚未配置 Outline 连接。")
        print()
        print("提示：执行 yzrws outline add 添加配置")
        return 0

    print_banner("Outline 配置")
    print()
    print(f"  {'KEY':<12}  VALUE")
    print(f"  {'-' * 12}  {'-' * 40}")
    print(f"  {'endpoint':<12}  {config.endpoint}")
    print(f"  {'auth_token':<12}  {mask_token(config.auth_token)}")
    print()
    print(f"配置文件：{outline_path}")
    return 0


# ==================================================================
# yzrws outline update
# ==================================================================


def run_update(args: argparse.Namespace) -> int:
    """实现 `yzrws outline update [--endpoint ...] [--auth-token ...] [-y]`."""
    workspace_path = paths.get_workspace_path()
    try:
        _require_workspace(workspace_path)
    except _AbortError:
        return 1

    outline_path = get_workspace_outline_path(workspace_path)
    existing = load_outline(outline_path)

    if existing is None:
        print(f"[{STATUS_ERROR}] Outline 配置不存在：{outline_path}")
        print()
        print("提示：执行 yzrws outline add 添加配置")
        return 1

    new_endpoint = args.endpoint
    new_auth_token = args.auth_token

    # 至少更新一个字段
    if not new_endpoint and not new_auth_token:
        print(f"[{STATUS_ERROR}] 至少需要指定 --endpoint 或 --auth-token 之一")
        return 1

    print_banner("更新 Outline 配置")
    print()
    print(f"目标文件：{outline_path}")
    print()

    try:
        # 更新 endpoint
        if new_endpoint:
            new_endpoint = _normalize_endpoint(new_endpoint)
            if not is_valid_endpoint(new_endpoint):
                print(f"[{STATUS_ERROR}] endpoint 不合法：{new_endpoint!r}")
                print(
                    "  endpoint 必须是 HTTPS URL（如 https://my-team.getoutline.com）"
                )
                return 1
            print(f"  endpoint: {existing.endpoint} → {new_endpoint}")
        else:
            new_endpoint = existing.endpoint

        # 更新 auth_token（敏感操作，需要二次确认）
        if new_auth_token:
            if not args.yes:
                print(f"  [{STATUS_WARN}] 即将更新 API key（敏感操作）")
                if not _confirm("确认更新？"):
                    print_user_aborted("更新 Outline 配置")
                    return 1
            print(
                f"  auth_token: {mask_token(existing.auth_token)} → {mask_token(new_auth_token)}"
            )
        else:
            new_auth_token = existing.auth_token
    except _AbortError:
        return 1

    config = OutlineConfig(endpoint=new_endpoint, auth_token=new_auth_token)
    save_outline(outline_path, config)

    print()
    print("=== 更新成功 ===")
    print()
    print("所有引用 'default' 的工作项下次 yzrws workitem start 将自动使用新配置。")
    return 0


# ==================================================================
# yzrws outline remove
# ==================================================================


def run_remove(args: argparse.Namespace) -> int:
    """实现 `yzrws outline remove [-y]`."""
    workspace_path = paths.get_workspace_path()
    try:
        _require_workspace(workspace_path)
    except _AbortError:
        return 1

    outline_path = get_workspace_outline_path(workspace_path)

    # 幂等：配置不存在时不报错
    if not outline_path.is_file():
        print("尚未配置 Outline 连接。")
        print()
        print("提示：执行 yzrws outline add 添加配置")
        return 0

    # 引用扫描（删除前）
    referencing = find_workitems_referencing_outline(workspace_path)

    print_banner("删除 Outline 配置")
    print()
    print(f"配置文件：{outline_path}")

    if not args.yes:
        if not _confirm("确认删除？"):
            print_user_aborted("删除 Outline 配置")
            return 1

    remove_outline(outline_path)
    print("  [删除] outline.json")

    # 引用警告
    if referencing:
        print()
        print(f"  [{STATUS_WARN}] 以下工作项仍引用 Outline 配置（'default'）：")
        for name in referencing:
            print(f"    - {name}")
        print()
        print(
            "  这些工作项下次 yzrws workitem start 时会打印 WARN（outline 配置缺失），"
        )
        print("  仍可正常启动但不会加载 Outline MCP。")
        print("  如需显式关闭，可执行：")
        for name in referencing:
            print(f"    yzrws workitem unset-outline {name}")

    print()
    print("=== 删除成功 ===")
    return 0


# 注册到顶层子命令表
REGISTRY["outline"] = run
