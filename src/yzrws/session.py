"""Session 管理工具函数。

设计参考 doc/session_design.md。

存储布局：

    <workitem>/
    ├── session.json                          # 指针：{"current": "<name>"}
    └── sessions/
        ├── <name>.json                       # 用户命名 session
        ├── ...
        └── _archive_<engine>_<timestamp>.json   # 引擎切换自动归档（下划线前缀）

所有上层入口在读 / 写 session 之前必须先调用 ``migrate_legacy_session`` 完成
旧格式（无 ``current`` 字段的 ``session.json`` / 无下划线前缀的旧归档）迁移；
迁移函数是幂等的。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yzrws.workspace import atomic_write_json

# Session 指针文件
_SESSION_FILE = "session.json"
# 历史 session 目录
_SESSIONS_DIR = "sessions"
# 引擎切换归档文件名前缀（下划线开头避免与用户命名 session 冲突）
_ARCHIVE_PREFIX = "_archive_"
# 用户命名 session 名字校验
_SESSION_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def _is_valid_session_filename(stem: str) -> bool:
    """文件名 stem 是否为合法的用户命名 session（不含下划线前缀）。"""
    if not stem or stem.startswith(_ARCHIVE_PREFIX):
        return False
    return bool(_SESSION_NAME_RE.match(stem))


@dataclass
class SessionInfo:
    """会话信息。

    Attributes:
        name: session 名（来自 ``sessions/<name>.json`` 的文件名）
        engine: 当前活跃的引擎
        session_id: 引擎原生的 session id
        status: 会话状态（active / paused / completed / archived）
        title: 用户给的标题（可选，list 时显示便于区分）
        model: 当前会话使用的模型
        provider: Provider 引用
        created_at: 创建时间（ISO 8601）
        updated_at: 最近一次 update 时间（ISO 8601）
        resume_count: 恢复次数（用于诊断）
        archived_at: 归档时间（仅归档 session 有）
    """

    name: str
    engine: str
    session_id: str
    status: str
    title: str = ""
    model: str | None = None
    provider: str | None = None
    created_at: str = ""
    updated_at: str = ""
    resume_count: int = 0
    archived_at: str = ""


def _session_path(workitem_dir: Path, name: str) -> Path:
    """构造 ``sessions/<name>.json`` 路径。name 非法时抛 ``ValueError``。"""
    if not _SESSION_NAME_RE.match(name):
        raise ValueError(f"非法的 session 名：{name!r}")
    return workitem_dir / _SESSIONS_DIR / f"{name}.json"


def _sessions_dir(workitem_dir: Path) -> Path:
    """返回 ``<workitem>/sessions`` 目录，确保存在。"""
    d = workitem_dir / _SESSIONS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_info(name: str, data: dict) -> SessionInfo:
    """将 JSON 字典转成 ``SessionInfo``。"""
    return SessionInfo(
        name=name,
        engine=str(data.get("engine", "")),
        session_id=str(data.get("session_id", "")),
        status=str(data.get("status", "paused")),
        title=str(data.get("title", "")),
        model=data.get("model"),
        provider=data.get("provider"),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        resume_count=int(data.get("resume_count", 0) or 0),
        archived_at=str(data.get("archived_at", "")),
    )


def _from_info(session: SessionInfo) -> dict:
    """将 ``SessionInfo`` 序列化为 JSON 字典。"""
    data: dict = {
        "engine": session.engine,
        "session_id": session.session_id,
        "status": session.status,
        "title": session.title,
        "model": session.model,
        "provider": session.provider,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "resume_count": session.resume_count,
    }
    if session.archived_at:
        data["archived_at"] = session.archived_at
    return data


# ==================================================================
# 指针文件：session.json 仅含 {"current": "<name>"}
# ==================================================================


def get_current_session_name(workitem_dir: Path) -> str | None:
    """读 ``session.json`` 拿 current session 名。

    Returns:
        session 名，或 None（文件不存在 / 解析失败 / ``current`` 为空时）。
    """
    session_path = workitem_dir / _SESSION_FILE
    if not session_path.is_file():
        return None
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    current = data.get("current")
    if not isinstance(current, str) or not current:
        return None
    if not _SESSION_NAME_RE.match(current):
        return None
    return current


def set_current_session_name(workitem_dir: Path, name: str | None) -> None:
    """原子写 ``{"current": <name>}``。``name=None`` 时写 ``{"current": null}``。"""
    session_path = workitem_dir / _SESSION_FILE
    atomic_write_json(session_path, {"current": name})


# ==================================================================
# 按名字读写
# ==================================================================


def read_session_by_name(workitem_dir: Path, name: str) -> SessionInfo | None:
    """读 ``sessions/<name>.json``，返回 ``SessionInfo`` 或 None。

    name 非法时抛 ``ValueError``；文件不存在 / 解析失败时返回 None。
    """
    if not _SESSION_NAME_RE.match(name):
        raise ValueError(f"非法的 session 名：{name!r}")
    path = _session_path(workitem_dir, name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _to_info(name, data)


def write_session(workitem_dir: Path, session: SessionInfo) -> None:
    """写 ``sessions/<session.name>.json``（原子写）。"""
    if not _SESSION_NAME_RE.match(session.name):
        raise ValueError(f"非法的 session 名：{session.name!r}")
    _sessions_dir(workitem_dir)  # 确保 sessions/ 存在
    atomic_write_json(_session_path(workitem_dir, session.name), _from_info(session))


def read_current_session(workitem_dir: Path) -> SessionInfo | None:
    """便捷函数：读 current 指针并返回对应的 ``SessionInfo``（找不到时 None）。"""
    name = get_current_session_name(workitem_dir)
    if name is None:
        return None
    return read_session_by_name(workitem_dir, name)


# ==================================================================
# 列举 / 删除
# ==================================================================


def list_sessions(workitem_dir: Path) -> list[SessionInfo]:
    """列举用户命名 session（按 updated_at 倒序，无该字段时按 mtime）。

    Returns:
        ``SessionInfo`` 列表，忽略下划线开头的归档文件。
    """
    sessions_root = workitem_dir / _SESSIONS_DIR
    if not sessions_root.is_dir():
        return []

    result: list[SessionInfo] = []
    for path in sessions_root.glob("*.json"):
        if not _is_valid_session_filename(path.stem):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        info = _to_info(path.stem, data)
        result.append(info)

    # 排序：updated_at 倒序；缺字段时按 mtime 倒序，且整体排在末尾。
    # 用 (has_updated, updated_or_empty, neg_mtime) 做 key；reverse=True 时
    # has_updated=1 的组排前面，has_updated=0 的组排末尾。
    def _sort_key(info: SessionInfo) -> tuple[int, str, float]:
        try:
            neg_mtime = -(_session_path(workitem_dir, info.name)).stat().st_mtime
        except OSError:
            neg_mtime = 0.0
        if info.updated_at:
            return (1, info.updated_at, neg_mtime)
        return (0, "", neg_mtime)

    result.sort(key=_sort_key, reverse=True)
    return result


def delete_session_by_name(workitem_dir: Path, name: str) -> bool:
    """删除 ``sessions/<name>.json``，返回是否真删。

    name 非法时抛 ``ValueError``。
    """
    if not _SESSION_NAME_RE.match(name):
        raise ValueError(f"非法的 session 名：{name!r}")
    path = _session_path(workitem_dir, name)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ==================================================================
# 引擎切换归档（下划线前缀）
# ==================================================================


def archive_session(workitem_dir: Path, session: SessionInfo) -> Path:
    """将 session 归档到 ``sessions/_archive_<engine>_<timestamp>.json``。

    引擎切换时由 ``start`` 调用——归档的是"被切换掉的旧 session"。

    Returns:
        归档文件路径。
    """
    sessions_root = _sessions_dir(workitem_dir)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    archive_name = f"{_ARCHIVE_PREFIX}{session.engine}_{timestamp}.json"
    archive_path = sessions_root / archive_name

    # 设置归档字段
    session.archived_at = datetime.now().astimezone().isoformat(timespec="seconds")
    session.status = "archived"

    atomic_write_json(archive_path, _from_info(session))
    return archive_path


def find_latest_session_for_engine(
    workitem_dir: Path, engine: str
) -> SessionInfo | None:
    """从 ``sessions/_archive_<engine>_*.json`` 找指定引擎的最新历史 session。

    Returns:
        ``SessionInfo``（status=archived），或 None（无历史 session 时）。
    """
    sessions_root = workitem_dir / _SESSIONS_DIR
    if not sessions_root.is_dir():
        return None

    pattern = f"{_ARCHIVE_PREFIX}{engine}_*.json"
    archives = list(sessions_root.glob(pattern))
    if not archives:
        return None

    archives.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = archives[0]

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None

    return _to_info(latest.stem, data)


# ==================================================================
# 迁移（旧格式 → 新格式）
# ==================================================================


def migrate_legacy_session(workitem_dir: Path) -> None:
    """把旧格式 session.json / sessions/<engine>_<ts>.json 迁移到新格式。

    旧格式形态：
      - ``<workitem>/session.json`` 含有 ``engine / session_id / status`` 等字段
        （无 ``current`` 键）——直接视为单一 session。
      - ``<workitem>/sessions/<engine>_<timestamp>.json`` —— 引擎切换归档，
        新格式要求下划线前缀 ``_archive_``。

    新格式下 ``session.json`` 仅含 ``{"current": <name>}``；旧归档统一
    重命名为 ``_archive_<engine>_<timestamp>.json``，避免与用户命名 session
    冲突。

    幂等：新格式下立即 return，可重复调用。
    """
    if not workitem_dir.is_dir():
        return

    session_path = workitem_dir / _SESSION_FILE
    sessions_root = workitem_dir / _SESSIONS_DIR

    # 0) 旧归档（``sessions/<engine>_<timestamp>.json``）一律重命名为 _archive_ 前缀
    #    —— 不论 session.json 是新格式还是旧格式都要做这一步。
    if sessions_root.is_dir():
        for p in sessions_root.glob("*.json"):
            if p.stem.startswith(_ARCHIVE_PREFIX):
                continue
            # 仅匹配 "<engine>_<timestamp>" 形态（engine 已知列表 + 下划线切分）
            if "_" not in p.stem:
                continue
            head = p.stem.split("_", 1)[0]
            if head not in {"claude-code", "opencode"}:
                continue
            new_path = p.with_name(f"{_ARCHIVE_PREFIX}{p.name}")
            # 极少见冲突：已经有同名 _archive_ 文件，跳过（保留旧文件）
            if not new_path.exists():
                p.rename(new_path)

    # 1) 旧 session.json 迁移
    if session_path.is_file():
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None

        if isinstance(data, dict) and "current" in data:
            # 已是新格式
            return

        # 旧格式：把数据搬到 sessions/default.json
        if isinstance(data, dict):
            sessions_root.mkdir(parents=True, exist_ok=True)
            target = sessions_root / "default.json"
            if target.is_file():
                # 极少见冲突：default 已被占用，加 timestamp 后缀
                ts = datetime.now().strftime("%Y%m%dT%H%M%S")
                target = sessions_root / f"default_{ts}.json"

            payload = dict(data)
            payload.setdefault("title", "")
            payload.setdefault("status", "paused")
            payload.setdefault("resume_count", 0)
            atomic_write_json(target, payload)
            atomic_write_json(session_path, {"current": target.stem})
        else:
            # JSON 损坏或不是 dict：保守写一个空指针，让 start 时创建 default
            atomic_write_json(session_path, {"current": None})
        return

    # 2) session.json 不存在但有旧 sessions/_archive_<engine>_<ts>.json：
    #    把最新一份还原为 default。注意：上面 step 0 已经把所有旧归档重命名
    #    过了，所以这里 glob 找的是 _archive_ 前缀的文件。
    if not sessions_root.is_dir():
        return

    legacy_archives = sorted(
        sessions_root.glob(f"{_ARCHIVE_PREFIX}*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not legacy_archives:
        return

    latest = legacy_archives[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return

    payload = dict(data)
    payload.setdefault("title", "")
    default_target = sessions_root / "default.json"
    if default_target.is_file():
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        default_target = sessions_root / f"default_{ts}.json"
    atomic_write_json(default_target, payload)
    atomic_write_json(session_path, {"current": default_target.stem})
