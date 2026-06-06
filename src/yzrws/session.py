"""Session 管理工具函数。

设计参考 doc/session_design.md。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yzrws.workspace import atomic_write_json

# Session 文件名
_SESSION_FILE = "session.json"
# 历史 session 归档目录
_SESSIONS_DIR = "sessions"


@dataclass
class SessionInfo:
    """会话信息。"""

    engine: str
    session_id: str
    status: str  # active / paused / completed / archived
    model: str | None = None
    provider: str | None = None
    created_at: str = ""
    updated_at: str = ""
    resume_count: int = 0
    archived_at: str = ""


def read_session(workitem_dir: Path) -> SessionInfo | None:
    """读取 session.json。

    Returns:
        SessionInfo 实例，或 None（文件不存在或解析失败时）
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

    return SessionInfo(
        engine=data.get("engine", ""),
        session_id=data.get("session_id", ""),
        status=data.get("status", "paused"),
        model=data.get("model"),
        provider=data.get("provider"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        resume_count=data.get("resume_count", 0),
        archived_at=data.get("archived_at", ""),
    )


def write_session(workitem_dir: Path, session: SessionInfo) -> None:
    """写入 session.json。"""
    session_path = workitem_dir / _SESSION_FILE
    data = {
        "engine": session.engine,
        "session_id": session.session_id,
        "status": session.status,
        "model": session.model,
        "provider": session.provider,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "resume_count": session.resume_count,
    }
    if session.archived_at:
        data["archived_at"] = session.archived_at

    atomic_write_json(session_path, data)


def archive_session(workitem_dir: Path, session: SessionInfo) -> Path:
    """将当前 session 归档到 sessions/ 目录。

    Args:
        workitem_dir: 工作项目录
        session: 要归档的 session 信息

    Returns:
        归档文件路径
    """
    # 确保 sessions 目录存在
    sessions_dir = workitem_dir / _SESSIONS_DIR
    sessions_dir.mkdir(exist_ok=True)

    # 生成归档文件名：<engine>_<timestamp>.json
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    archive_name = f"{session.engine}_{timestamp}.json"
    archive_path = sessions_dir / archive_name

    # 添加 archived_at 字段
    session.archived_at = datetime.now().astimezone().isoformat(timespec="seconds")
    session.status = "archived"

    data = {
        "engine": session.engine,
        "session_id": session.session_id,
        "status": session.status,
        "model": session.model,
        "provider": session.provider,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "resume_count": session.resume_count,
        "archived_at": session.archived_at,
    }
    atomic_write_json(archive_path, data)

    return archive_path


def find_latest_session_for_engine(
    workitem_dir: Path, engine: str
) -> SessionInfo | None:
    """从 sessions/ 目录查找指定引擎的最新历史 session。

    Args:
        workitem_dir: 工作项目录
        engine: 引擎名称

    Returns:
        SessionInfo 实例，或 None（无历史 session 时）
    """
    sessions_dir = workitem_dir / _SESSIONS_DIR
    if not sessions_dir.is_dir():
        return None

    # 查找匹配引擎的归档文件
    pattern = f"{engine}_*.json"
    archives = list(sessions_dir.glob(pattern))

    if not archives:
        return None

    # 按修改时间排序，取最新
    archives.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = archives[0]

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    return SessionInfo(
        engine=data.get("engine", engine),
        session_id=data.get("session_id", ""),
        status=data.get("status", "archived"),
        model=data.get("model"),
        provider=data.get("provider"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        resume_count=data.get("resume_count", 0),
        archived_at=data.get("archived_at", ""),
    )


def delete_session(workitem_dir: Path) -> None:
    """删除 session.json（如果存在）。"""
    session_path = workitem_dir / _SESSION_FILE
    if session_path.is_file():
        session_path.unlink()
