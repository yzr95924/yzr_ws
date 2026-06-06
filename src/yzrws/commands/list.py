"""yzrws list 命令实现：列举工作项及其元数据。

设计参考 doc/command_design.md §列举 workitem。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from yzrws import paths
from yzrws.commands import REGISTRY
from yzrws.commands._workspace_check import is_workspace_initialized
from yzrws.output import (
    print_list_empty,
    print_list_header,
    print_list_row,
    print_list_table_header,
    print_workspace_not_initialized,
)

# 顶层 --help 显示的简短描述（cli.py 的 _command_help 读取此属性）
HELP = "列举所有工作项及其元数据"

# 列最小宽度（表头文本长度作为下限）
_MIN_COL_WIDTHS = {"name": 4, "status": 6, "engine": 6, "created": 10}

# 缺失字段时显示的占位符
_MISSING = "—"


@dataclass(frozen=True)
class WorkitemInfo:
    """从 workitem.json 和 setting.json 读取的工作项元数据。"""

    name: str
    status: str
    engine: str
    created_at: str  # ISO 8601 原始值
    created_display: str  # 格式化后的显示值（YYYY-MM-DD 或 —）


def run(args: argparse.Namespace) -> int:
    """执行 `yzrws list`，返回进程退出码（0 = 成功，1 = 失败）。

    流程：
      1. 检查 workspace 是否已初始化
      2. 扫描 workspace 下包含 workitem.json 的子目录
      3. 读取每个工作项的元数据
      4. 按 created_at 降序排序并打印表格
    """
    # 处理 --help
    if args.subcmd_argv and args.subcmd_argv[0] in ("-h", "--help"):
        print("用法: yzrws list")
        print()
        print(HELP)
        print()
        print("显示所有工作项的名称、状态、引擎和创建时间。")
        return 0

    workspace_path = paths.get_workspace_path()

    # 1. 前置检查
    if not is_workspace_initialized(workspace_path):
        print_workspace_not_initialized(workspace_path)
        return 1

    # 2. 扫描工作项
    workitems = _scan_workitems(workspace_path)

    # 3. 打印报告
    print_list_header()

    if not workitems:
        print_list_empty()
        return 0

    # 4. 按 created_at 降序排序（最新的在前）
    workitems.sort(key=lambda w: w.created_at, reverse=True)

    # 5. 计算列宽并打印表格
    col_widths = _compute_col_widths(workitems)
    print_list_table_header(col_widths)
    for w in workitems:
        print_list_row(w.name, w.status, w.engine, w.created_display, col_widths)

    return 0


# ==================================================================
# 工作项扫描
# ==================================================================


def _scan_workitems(workspace_path: Path) -> list[WorkitemInfo]:
    """扫描 workspace 下所有包含 workitem.json 的子目录。

    跳过以下情况：
      - 非目录条目（文件、符号链接等）
      - 无 workitem.json 的目录
      - workitem.json 解析失败的目录
    """
    workitems: list[WorkitemInfo] = []

    if not workspace_path.is_dir():
        return workitems

    for entry in sorted(workspace_path.iterdir()):
        if not entry.is_dir():
            continue
        workitem_json = entry / "workitem.json"
        if not workitem_json.is_file():
            continue
        info = _read_workitem_info(entry, workitem_json)
        if info is not None:
            workitems.append(info)

    return workitems


def _read_workitem_info(dir_path: Path, workitem_json: Path) -> WorkitemInfo | None:
    """读取单个工作项的元数据。解析失败时返回 None。"""
    try:
        data = json.loads(workitem_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name", dir_path.name)
    status = data.get("status", _MISSING)
    created_at = data.get("created_at", "")

    # 读取 setting.json 获取引擎信息（可选，缺失不影响显示）
    engine = _read_engine(dir_path)

    # 格式化日期为 YYYY-MM-DD
    created_display = _format_date(created_at)

    return WorkitemInfo(
        name=str(name) if name else dir_path.name,
        status=str(status) if status else _MISSING,
        engine=engine,
        created_at=str(created_at) if created_at else "",
        created_display=created_display,
    )


def _read_engine(dir_path: Path) -> str:
    """从 setting.json 读取 engine 字段，缺失时返回占位符。"""
    setting_json = dir_path / "setting.json"
    if not setting_json.is_file():
        return _MISSING
    try:
        data = json.loads(setting_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _MISSING
    if not isinstance(data, dict):
        return _MISSING
    engine = data.get("engine")
    return str(engine) if engine else _MISSING


def _format_date(iso_str: str) -> str:
    """将 ISO 8601 时间戳格式化为 YYYY-MM-DD。解析失败时返回占位符。

    支持格式：
      - 完整 ISO 8601（带时区）：2026-06-06T12:00:00+08:00
      - 仅日期部分：2026-06-06
      - 空字符串或无效格式：返回 —
    """
    if not iso_str:
        return _MISSING
    # 取 T 之前的日期部分
    date_part = iso_str.split("T")[0]
    # 简单验证格式：YYYY-MM-DD（10 个字符）
    if len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-":
        return date_part
    return _MISSING


# ==================================================================
# 列宽计算
# ==================================================================


def _compute_col_widths(workitems: list[WorkitemInfo]) -> dict[str, int]:
    """根据实际数据动态计算列宽，保证表头和数据对齐。

    每列宽度 = max(表头文本长度, 该列所有数据值的最大长度)
    """
    widths = dict(_MIN_COL_WIDTHS)

    for w in workitems:
        widths["name"] = max(widths["name"], len(w.name))
        widths["status"] = max(widths["status"], len(w.status))
        widths["engine"] = max(widths["engine"], len(w.engine))
        widths["created"] = max(widths["created"], len(w.created_display))

    return widths


# 注册到子命令表
REGISTRY["list"] = run
