"""workspace 路径解析。"""

import os
from pathlib import Path

# 默认 workspace 路径。运行时支持 YZR_WORKSPACE 环境变量覆盖（详见 README）。
DEFAULT_WORKSPACE = "~/yzr_workspace"


def get_workspace_path() -> Path:
    """返回 workspace 路径：优先读 YZR_WORKSPACE 环境变量，空串视为未设置；否则用默认。

    返回的路径已展开 `~`（例如 `~/yzr_workspace` → `/Users/<user>/yzr_workspace`），
    调用方无需再 `expanduser`。
    """
    raw = os.environ.get("YZR_WORKSPACE", "").strip() or DEFAULT_WORKSPACE
    return Path(raw).expanduser()
