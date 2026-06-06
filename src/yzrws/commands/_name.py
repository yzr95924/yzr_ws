"""workitem 名称校验。

设计参考 doc/workitem_create_design.md §命名规则。
所有需要校验 workitem 名称的命令（create / start / workitem）共享。
"""

from __future__ import annotations

import re

# workitem 名称正则：小写字母 / 数字开头，可含连字符和下划线，长度 1-64
WORKITEM_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# 保留名称：与工作区顶层目录或内部概念冲突
WORKITEM_RESERVED_NAMES = frozenset({"knowledge", "config", "raw"})


def is_valid_workitem_name(name: str) -> bool:
    """校验 workitem 名称是否合法。True = 合法。

    规则（对齐 doc/workitem_create_design.md §命名规则）：
      - 正则 ^[a-z0-9][a-z0-9_-]{0,63}$
      - 不在保留名集合中
    """
    if not WORKITEM_NAME_RE.match(name):
        return False
    return name not in WORKITEM_RESERVED_NAMES
