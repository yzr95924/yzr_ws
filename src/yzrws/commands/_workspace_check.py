"""workspace 初始化检查。

所有需要检查 workspace 状态的命令（create / list / start / workitem / model）
共享；统一语义为"True = 已初始化"（与早期 create.py 内部的"True = 未初始化"
反转语义相比更直观，2026-06 重构时统一）。
"""

from __future__ import annotations

from pathlib import Path


def is_workspace_initialized(workspace_path: Path) -> bool:
    """检查 workspace 是否已初始化。True = 已初始化。

    判定条件：
      - workspace_path 是目录
      - workspace_path/metadata.json 是文件
    """
    if not workspace_path.is_dir():
        return False
    return (workspace_path / "metadata.json").is_file()
