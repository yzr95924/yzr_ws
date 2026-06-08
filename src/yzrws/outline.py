"""Outline Wiki MCP 配置读写与校验。

设计参考 doc/outline_wiki_design.md。

配置位置（单 endpoint）：<workspace>/.config/outline.json

outline.json 的 schema：
  {
    "endpoint": "https://<subdomain>.getoutline.com",
    "auth_token": "ol_api_xxxxxxxxxxxxxxxx"
  }

关键不变量：
  - 写盘使用 atomic_write_json（tempfile + os.replace），写失败不留半截 JSON。
  - 读盘失败（JSON 损坏 / 字段缺失）时返回 None，由 caller 决定降级行为。
  - endpoint 校验：scheme 必须为 https，必须有 netloc。
  - auth_token 非空字符串，不做长度强制校验。
  - 启动时 outline.json 缺失或字段损坏 → 不报错，打印 WARN 并跳过。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yzrws.workspace import atomic_write_json

# ==================================================================
# 路径
# ==================================================================

# Workspace 级 Outline 配置文件相对路径
WORKSPACE_OUTLINE_REL = Path(".config/outline.json")

# Workitem 唯一合法的引用名（单 endpoint 设计）
DEFAULT_REF = "default"

# Outline MCP 中执行写操作的工具名（用于 read-only 模式的 deny 列表）。
# 引擎适配器在构造 deny 条目时拼接前缀：f"mcp__outline__{tool}"。
# 工具名对齐 Outline MCP server 暴露的 tool name（不含 outline_ 前缀）。
OUTLINE_WRITE_TOOLS = (
    "create_document",
    "update_document",
    "archive_document",
    "create_comment",
)


# ==================================================================
# 异常
# ==================================================================


class OutlineConfigError(Exception):
    """Outline 配置相关的业务异常。"""


# ==================================================================
# 数据类
# ==================================================================


@dataclass(frozen=True)
class OutlineConfig:
    """Outline 连接配置。

    Attributes:
        endpoint: Outline 实例 URL（不含 /mcp 路径，不含尾随 /）。
        auth_token: Outline API key（明文存储）。
    """

    endpoint: str
    auth_token: str


# ==================================================================
# 路径解析
# ==================================================================


def get_workspace_outline_path(workspace: Path) -> Path:
    """返回 workspace 级 outline.json 的绝对路径。"""
    return workspace / WORKSPACE_OUTLINE_REL


# ==================================================================
# 校验
# ==================================================================


def is_valid_endpoint(url: str) -> bool:
    """校验 endpoint URL 是否合法。

    规则（对齐 doc/outline_wiki_design.md §校验规则）：
      - scheme 必须为 https
      - 必须有 netloc（域名 / 端口）
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def mask_token(token: str) -> str:
    """对 auth_token 脱敏：前 8 + 末 2 字符，中间 * 填充。

    长度不足 12 时仅显示前 2 + 末 1 + 中间 *。
    """
    if len(token) >= 12:
        return token[:8] + "*" * (len(token) - 10) + token[-2:]
    if len(token) >= 4:
        return token[:2] + "*" * (len(token) - 3) + token[-1:]
    return "***"


# ==================================================================
# 读 / 写 / 删
# ==================================================================


def load_outline(path: Path) -> OutlineConfig | None:
    """从指定路径加载 Outline 配置。

    Args:
        path: outline.json 的路径。

    Returns:
        OutlineConfig 实例；文件不存在或字段损坏时返回 None。
    """
    if not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not raw.strip():
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    endpoint = data.get("endpoint")
    auth_token = data.get("auth_token")

    if not isinstance(endpoint, str) or not endpoint:
        return None
    if not isinstance(auth_token, str) or not auth_token:
        return None

    return OutlineConfig(endpoint=endpoint, auth_token=auth_token)


def save_outline(path: Path, config: OutlineConfig) -> None:
    """将 Outline 配置写入指定路径，原子写。"""
    payload = {
        "endpoint": config.endpoint,
        "auth_token": config.auth_token,
    }
    atomic_write_json(path, payload)


def remove_outline(path: Path) -> bool:
    """删除 Outline 配置文件，幂等。

    Returns:
        True 表示文件确实被删除；False 表示文件本就不存在。
    """
    if path.is_file():
        path.unlink()
        return True
    return False


# ==================================================================
# MCP 配置构造
# ==================================================================


def build_mcp_config(config: OutlineConfig) -> dict:
    """从 OutlineConfig 构造引擎中性的 mcp_config dict。

    返回格式（yzrws 内部表示，沿用 MCP 规范 transport 命名）：
      {
        "outline": {
          "type": "http",
          "url": "<endpoint>/mcp",
          "headers": {
            "Authorization": "Bearer <auth_token>"
          }
        }
      }
    """
    # endpoint 末尾去尾随 /（容错）
    endpoint = config.endpoint.rstrip("/")
    return {
        "outline": {
            "type": "http",
            "url": f"{endpoint}/mcp",
            "headers": {
                "Authorization": f"Bearer {config.auth_token}",
            },
        },
    }


# ==================================================================
# 引用解析（yzrws workitem start 消费）
# ==================================================================


def resolve_mcp_config(
    setting: dict,
    workspace_path: Path,
) -> dict | None:
    """按 doc/outline_wiki_design.md §解析逻辑 解析 workitem 最终生效的 MCP 配置。

    Args:
        setting: workitem `setting.json` 的 dict 表示。
        workspace_path: workspace 根目录路径。

    Returns:
        mcp_config dict（可直接传给 engine.sync_mcp()），或 None（不启用）。
        降级场景会打印 WARN 到 stdout。
    """
    from yzrws.output import STATUS_WARN

    outline_ref = setting.get("outline")

    # null / 字段缺失 → 不启用
    if outline_ref is None:
        return None

    # 非字符串 → 视为未设置
    if not isinstance(outline_ref, str) or not outline_ref:
        return None

    # 引用名不为 "default" → WARN 并跳过
    if outline_ref != DEFAULT_REF:
        print(
            f"[{STATUS_WARN}] workitem 引用了不存在的 Outline 配置"
            f" {outline_ref!r}（仅支持 {DEFAULT_REF!r}），跳过 MCP 注入"
        )
        return None

    # 加载 outline.json
    outline_path = get_workspace_outline_path(workspace_path)
    config = load_outline(outline_path)

    if config is None:
        print(
            f"[{STATUS_WARN}] workitem 引用了 Outline 配置 {DEFAULT_REF!r}，"
            f"但 {outline_path} 缺失或损坏，跳过 MCP 注入"
        )
        print(
            "  提示：执行 yzrws outline add 添加配置，"
            "或 yzrws workitem unset-outline 解除引用"
        )
        return None

    # auth_token 为空字符串（不应到达——load_outline 已过滤，防御性检查）
    if not config.auth_token:
        print(f"[{STATUS_WARN}] Outline 配置的 auth_token 为空，跳过 MCP 注入")
        return None

    return build_mcp_config(config)


# ==================================================================
# 引用扫描（yzrws outline remove 消费）
# ==================================================================


def find_workitems_referencing_outline(workspace_path: Path) -> list[str]:
    """扫描 workspace 下所有 workitem 的 setting.json，返回引用了 outline 的名称。

    引用条件：setting.json.outline 字段为真值字符串（不为 null / 缺失）。
    """
    referencing: list[str] = []

    for child in sorted(workspace_path.iterdir()):
        if not child.is_dir():
            continue
        setting_path = child / "setting.json"
        if not setting_path.is_file():
            continue
        try:
            data = json.loads(setting_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        outline_ref = data.get("outline")
        if isinstance(outline_ref, str) and outline_ref:
            referencing.append(child.name)

    return referencing
