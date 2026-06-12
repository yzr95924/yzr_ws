"""workitem / session 名称校验。

设计参考 doc/workitem_create_design.md §命名规则 与 doc/session_design.md §命名规则。
所有需要校验名称的命令（create / start / workitem / workitem session）共享。
"""

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


# session 名称正则：小写字母 / 数字开头，可含连字符和下划线，长度 1-32。
# 与 Provider 命名规则保持一致（doc/provider_design.md）。
SESSION_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def is_valid_session_name(name: str) -> bool:
    """校验 session 名称是否合法。True = 合法。

    规则（对齐 doc/session_design.md §命名规则）：
      - 正则 ^[a-z0-9][a-z0-9_-]{0,31}$（1-32 字符，小写字母 / 数字开头）
    """
    if not SESSION_NAME_RE.match(name):
        return False
    return True
