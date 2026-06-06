"""自检报告格式化与状态标签常量。

状态标签统一在此集中维护，避免散落在各命令的 print 字符串中。
后续命令（create / list / import 等）应复用这些常量。

报告分块打印：caller 先 print_banner 与 header，调用业务逻辑；
    业务逻辑成功返回 CheckItem 列表时，调用 print_items + footer；
    业务逻辑抛出 fatal 异常时，调用 print_failure。
这样 caller 可以完整控制异常路径上"是否打印路径行"的细节。
"""

import unicodedata
from dataclasses import dataclass
from pathlib import Path

# ---- 状态标签（中文，与设计文档 doc/workspace_init_design.md 对齐）----
STATUS_EXISTS = "已存在"
STATUS_CREATED = "创建"
STATUS_ERROR = "错误"
STATUS_WARN = "警告"


@dataclass(frozen=True)
class CheckItem:
    """单条自检项。

    Attributes:
        name: 人类可读的检查项名称，例如 "workspace 目录" / "metadata.json"。
        path: 对应的物理路径；field 类检查项指向被检查的容器文件。
        kind: "directory" / "file" / "field"，用于报告排序与图标决策。
        status: STATUS_* 常量之一。
        note: 附加说明，例如版本号、损坏原因等；为空时不在报告中显示。
    """

    name: str
    path: Path | None
    kind: str
    status: str
    note: str = ""


def print_banner(title: str) -> None:
    """打印顶级 banner：=== title ===。"""
    print(f"=== {title} ===")


def _display_width(text: str) -> int:
    """计算字符串在等宽终端里的显示宽度（CJK 算 2 列）。"""
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def print_items(items: list[CheckItem]) -> None:
    """逐行打印自检项，不含头尾装饰。

    状态标签按显示宽度对齐到本批 items 中的最宽标签，
    使 name 列起点一致（与设计文档样例一致）。
    """
    if not items:
        return
    max_tag_width = max(_display_width(f"[{item.status}]") for item in items)
    for item in items:
        tag = f"[{item.status}]"
        pad = " " * (max_tag_width - _display_width(tag))
        if item.note:
            print(f"  {tag}{pad} {item.name}  {item.note}")
        else:
            print(f"  {tag}{pad} {item.name}")


def print_init_footer(has_error: bool) -> None:
    """打印 init 报告底部状态行。"""
    if has_error:
        print("=== 初始化失败 ===")
    else:
        print("=== 自检通过，workspace 已就绪 ===")


def print_failure(message: str, hint: str = "") -> None:
    """打印致命错误信息（前置检查失败场景）。

    输出格式与设计文档 doc/workspace_init_design.md 第 267-278 行的样例对齐：
        [错误] <message>
               <hint>   (仅当 hint 非空)

    === 初始化失败 ===
    """
    print(f"  [{STATUS_ERROR}] {message}")
    if hint:
        print(f"         {hint}")
    print()
    print("=== 初始化失败 ===")
