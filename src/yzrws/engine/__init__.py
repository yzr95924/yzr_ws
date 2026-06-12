"""Agent 引擎模块。

提供引擎抽象基类和工厂函数，供 start 命令调度不同的 Agent 引擎。
"""

from typing import Dict, List, Type

from .base import AgentEngine
from .claude_code import ClaudeCodeEngine
from .opencode import OpenCodeEngine

# 引擎注册表：引擎名称 → 适配器类
_ENGINES: Dict[str, Type[AgentEngine]] = {
    "claude-code": ClaudeCodeEngine,
    "opencode": OpenCodeEngine,
}


def get_engine(name: str) -> AgentEngine:
    """根据引擎名称获取适配器实例。

    Args:
        name: 引擎名称（"claude-code" / "opencode"）

    Returns:
        引擎适配器实例

    Raises:
        ValueError: 未知的引擎名称
    """
    engine_cls = _ENGINES.get(name)
    if engine_cls is None:
        supported = ", ".join(sorted(_ENGINES.keys()))
        raise ValueError(f"未知引擎: {name}（支持的引擎: {supported}）")
    return engine_cls()


def list_engines() -> List[str]:
    """返回所有支持的引擎名称列表。"""
    return sorted(_ENGINES.keys())


__all__ = ["AgentEngine", "get_engine", "list_engines"]
