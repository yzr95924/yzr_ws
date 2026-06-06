"""workspace 初始化与自检业务逻辑。

设计参考 doc/workspace_init_design.md。

关键不变量：
  - 决定"是否写入"只来自 path.exists()，不来自 CheckItem.status。
    即 check 与 act 解耦：先 inspect 一次得到现状，执行创建，再 inspect
    一次得到最终状态用于报告。
  - 文件写入使用 tempfile + os.replace，保证原子性。
    写失败时清理临时文件，不留半截 JSON。
  - metadata.json 只在 init 阶段写入最小集 {version, created_at, updated_at}，
    其他字段（stats / recent_workitems / name / description）由后续命令按需维护。
    这与 metadata_design.md "完整 schema 由其他命令在运行过程中逐步填充" 一致。

版本比较说明：
  当前 EXPECTED_METADATA_VERSION = "1.0"，字符串比较与语义比较一致。
  假设未来引入 "1.0.0" / "1.1" / "2.0" 等形式版本时，需切换为
  tuple(int(x) for x in v.split(".")) 比较。
"""

import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path

from .errors import WritePermissionError
from .output import (
    STATUS_CREATED,
    STATUS_ERROR,
    STATUS_EXISTS,
    STATUS_WARN,
    CheckItem,
)

EXPECTED_METADATA_VERSION = "1.0"

# MEMORY.md 骨架内容，严格按设计文档第 190-194 行。
MEMORY_SKELETON = (
    "# MEMORY.md — 跨工作项长期记忆\n"
    "\n"
    "> 本文件记录跨工作项的长期决策与偏好。\n"
    "> 工作项内部的记忆请写到对应工作项目录下的 CLAUDE.md 中。\n"
)


class TerminalState(Enum):
    """workspace 路径的前置检查终态。"""

    OCCUPIED = "occupied"  # 致命：路径存在但是文件
    NO_PERMISSION = "no_perm"  # 致命：路径（或父目录）无写权限
    READY = "ready"  # 可继续（覆盖"全新"与"已存在"两种情况）


class InitFatalError(Exception):
    """init 流程中的致命错误（路径被占用 / 无写权限等）。

    继承 YzrwsError 以便上层用 except YzrwsError 统一捕获。
    携带 message + hint 两个字段，让 caller 决定如何展示。
    """

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class InspectionResult:
    """一次 inspect_state 的结果。"""

    terminal: TerminalState
    items: list[CheckItem]
    metadata_version: str | None  # None = 文件缺失或 JSON 损坏
    metadata_raw_error: str = ""  # JSON 损坏时的错误信息


# ==================================================================
# 基础工具
# ==================================================================


def now_iso() -> str:
    """返回带本地时区偏移的 ISO 8601 时间戳。

    使用 astimezone() 而非裸 datetime.now()，保证带 "+08:00" 这类偏移，
    与设计文档示例一致。
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_text(path: Path, content: str) -> None:
    """原子写入文本：tmp + os.replace。写失败时清理 tmp。"""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_json(path: Path, data: dict) -> None:
    """原子写入 JSON 对象，ensure_ascii=False 以保留中文可读性。"""
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, payload)


def _check_writable(workspace: Path) -> None:
    """检查写入权限：路径存在时检查自身，不存在时检查父目录。

    os.access 在路径不存在时返回 False，所以必须显式切到 parent。
    """
    target = workspace if workspace.exists() else workspace.parent
    if not os.access(target, os.W_OK):
        raise WritePermissionError(target)


# ==================================================================
# metadata.json 读取
# ==================================================================


def _read_metadata_version(metadata_path: Path) -> tuple[str | None, str]:
    """读取 metadata.json 的 version 字段。

    Returns:
        (version, "")         成功读取
        (None, "")            文件不存在（正常情况，不算错误）
        (None, error_message) 文件存在但 JSON 损坏或字段缺失
    """
    if not metadata_path.exists():
        return None, ""
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败：{e.msg}"
    version = data.get("version")
    if not isinstance(version, str):
        return None, "version 字段缺失或类型错误"
    return version, ""


def _version_note(actual: str) -> str:
    """根据 actual 与 EXPECTED 的关系，生成 version 字段项的 note。"""
    if actual == EXPECTED_METADATA_VERSION:
        return f"v{actual}"
    if actual < EXPECTED_METADATA_VERSION:
        return (
            f"v{actual}，当前期望 v{EXPECTED_METADATA_VERSION}，建议运行 yzrws migrate"
        )
    return (
        f"v{actual} 高于当前工具支持的 v{EXPECTED_METADATA_VERSION}，请升级 yzrws 工具"
    )


def _version_status(actual: str) -> str:
    """比较 actual 与 EXPECTED_METADATA_VERSION，返回 STATUS_*。"""
    if actual == EXPECTED_METADATA_VERSION:
        return STATUS_EXISTS
    if actual < EXPECTED_METADATA_VERSION:
        return STATUS_WARN
    return STATUS_ERROR


# ==================================================================
# 检查清单构造
# ==================================================================


def _build_items(
    workspace: Path,
    metadata_version: str | None,
    metadata_raw_error: str,
) -> list[CheckItem]:
    """构造 6 项自检清单。

    每项的 status 是"检查时刻"的状态：
      - 已存在的目录 / 文件 → STATUS_EXISTS
      - 缺失的目录 / 文件 → STATUS_CREATED（表示"期望 init 时创建"）
      - version 字段 → 视 actual 与 EXPECTED 的关系返回 STATUS_EXISTS / WARN / ERROR

    注意：status 仅是"现状描述"，不参与"是否要写入"的决策。
    """
    knowledge = workspace / "knowledge"
    config_dir = workspace / ".config"
    metadata = workspace / "metadata.json"
    memory = workspace / "MEMORY.md"

    if metadata_version is not None:
        version_status = _version_status(metadata_version)
        version_note = _version_note(metadata_version)
    elif metadata_raw_error:
        version_status = STATUS_WARN
        version_note = metadata_raw_error
    else:
        version_status = STATUS_CREATED
        version_note = ""

    return [
        CheckItem("workspace 目录", workspace, "directory", STATUS_EXISTS),
        CheckItem(
            "knowledge/",
            knowledge,
            "directory",
            STATUS_EXISTS if knowledge.exists() else STATUS_CREATED,
        ),
        CheckItem(
            ".config/",
            config_dir,
            "directory",
            STATUS_EXISTS if config_dir.exists() else STATUS_CREATED,
        ),
        CheckItem(
            "metadata.json",
            metadata,
            "file",
            STATUS_EXISTS if metadata.exists() else STATUS_CREATED,
        ),
        CheckItem(
            "metadata.json.version 字段",
            metadata,
            "field",
            version_status,
            note=version_note,
        ),
        CheckItem(
            "MEMORY.md",
            memory,
            "file",
            STATUS_EXISTS if memory.exists() else STATUS_CREATED,
        ),
    ]


# ==================================================================
# inspect / init
# ==================================================================


def inspect_state(workspace: Path) -> InspectionResult:
    """检查 workspace 路径当前状态，不做任何修改。

    Raises:
        不抛异常；致命情况以 terminal 字段表达，由调用方分支处理。
    """
    if workspace.exists() and not workspace.is_dir():
        return InspectionResult(
            terminal=TerminalState.OCCUPIED,
            items=[
                CheckItem(
                    "workspace 路径",
                    workspace,
                    "directory",
                    STATUS_ERROR,
                    note="路径存在但是文件",
                ),
            ],
            metadata_version=None,
        )

    try:
        _check_writable(workspace)
    except WritePermissionError as e:
        return InspectionResult(
            terminal=TerminalState.NO_PERMISSION,
            items=[
                CheckItem(
                    "workspace 路径",
                    workspace,
                    "directory",
                    STATUS_ERROR,
                    note=str(e),
                ),
            ],
            metadata_version=None,
        )

    metadata = workspace / "metadata.json"
    metadata_version, raw_error = _read_metadata_version(metadata)
    items = _build_items(workspace, metadata_version, raw_error)
    return InspectionResult(
        terminal=TerminalState.READY,
        items=items,
        metadata_version=metadata_version,
        metadata_raw_error=raw_error,
    )


def _ensure_directory(path: Path) -> bool:
    """确保目录存在。返回是否本次新建。"""
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def _ensure_gitkeep(directory: Path) -> None:
    """若目录中尚无 .gitkeep，写入空 .gitkeep 以支持版本控制。"""
    gitkeep = directory / ".gitkeep"
    if gitkeep.exists():
        return
    atomic_write_text(gitkeep, "")


def _write_metadata_if_missing(workspace: Path) -> bool:
    """若 metadata.json 缺失，原子写入最小初始集；返回是否本次写入。

    已存在则不动：可能是更早 init 留下的，也可能是用户手工写的，
    覆盖会丢失信息。init 之后 metadata 的扩展由后续命令按需维护。
    """
    metadata = workspace / "metadata.json"
    if metadata.exists():
        return False
    now = now_iso()
    payload = {
        "version": EXPECTED_METADATA_VERSION,
        "created_at": now,
        "updated_at": now,
    }
    atomic_write_json(metadata, payload)
    return True


def _write_memory_if_missing(workspace: Path) -> bool:
    """若 MEMORY.md 缺失，原子写入 4 行骨架；返回是否本次写入。已存在则不动。"""
    memory = workspace / "MEMORY.md"
    if memory.exists():
        return False
    atomic_write_text(memory, MEMORY_SKELETON)
    return True


def init(workspace: Path) -> list[CheckItem]:
    """执行 workspace 初始化，返回用于报告的 CheckItem 列表。

    行为：
      - 路径被文件占用 → 抛 InitFatalError（caller 用 print_failure 展示）
      - 无写权限 → 抛 InitFatalError
      - 全新或部分存在 → 创建缺失项，幂等，不覆盖已有内容
      - 完成后重新 inspect 一次，把最终状态交给 caller 报告

    Raises:
        InitFatalError: 致命前置检查失败。
    """
    initial = inspect_state(workspace)

    if initial.terminal == TerminalState.OCCUPIED:
        raise InitFatalError(
            f"{workspace} 是一个文件，不是目录",
            hint="请移除该文件或指定其他路径",
        )
    if initial.terminal == TerminalState.NO_PERMISSION:
        raise InitFatalError(
            f"对 {workspace} 无写权限",
            hint="请检查路径权限后重试",
        )

    # READY 分支：补全缺失项，并跟踪本次创建路径用于报告展示。
    # workspace 目录本身不在跟踪集内——按设计文档样例，它在报告里
    # 始终是 [已存在]（不论是刚 mkdir 还是早已存在）。
    workspace.mkdir(parents=True, exist_ok=True)
    created_paths: set[Path] = set()

    knowledge = workspace / "knowledge"
    if _ensure_directory(knowledge):
        created_paths.add(knowledge)
        _ensure_gitkeep(knowledge)

    config_dir = workspace / ".config"
    if _ensure_directory(config_dir):
        created_paths.add(config_dir)
        _ensure_gitkeep(config_dir)

    if _write_metadata_if_missing(workspace):
        created_paths.add(workspace / "metadata.json")
    if _write_memory_if_missing(workspace):
        created_paths.add(workspace / "MEMORY.md")

    # 完成后重新检查，得到真实最终状态；并把"本次创建"标记上去。
    final = inspect_state(workspace)
    return [
        replace(item, status=STATUS_CREATED)
        if item.kind in ("directory", "file") and item.path in created_paths
        else item
        for item in final.items
    ]
