"""子命令注册表。

每个子模块（init / create / list / import / ...）在文件末尾把自己的 run 函数
注册到 REGISTRY，cli.py 通过 REGISTRY[args.command] 查表分发。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

# 命令名 → run(args) -> int 调度函数
REGISTRY: dict[str, Callable[["argparse.Namespace"], int]] = {}

# 触发子模块的副作用：模块 import 时执行 REGISTRY[...] = run
from . import init as _init  # noqa: E402, F401
