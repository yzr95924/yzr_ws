"""Agent 引擎抽象基类。

定义所有 Agent 引擎必须实现的统一接口，供 start 命令调用。
设计参考 doc/multi_agent_design.md。
"""

from abc import ABC, abstractmethod
from pathlib import Path

from yzrws.provider import ResolvedModel


class AgentEngine(ABC):
    """Agent 引擎抽象基类。

    所有引擎适配器必须继承此类并实现抽象方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎标识符（如 "claude-code" / "opencode"）。"""

    @abstractmethod
    def start(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,
    ) -> int:
        """启动新的交互式会话。

        Args:
            workitem_dir: 工作项目录路径
            model: 按回退链解析后的最终模型配置（None 表示使用引擎内置默认）

        Returns:
            进程退出码（0 = 成功）
        """

    @abstractmethod
    def resume(
        self,
        workitem_dir: Path,
        session_id: str,
        *,
        model: ResolvedModel | None = None,
    ) -> int:
        """恢复指定会话。

        Args:
            workitem_dir: 工作项目录路径
            session_id: 要恢复的 session ID
            model: 按回退链解析后的最终模型配置

        Returns:
            进程退出码（0 = 成功）
        """

    @abstractmethod
    def extract_session_id(self, workitem_dir: Path) -> str | None:
        """从引擎本地存储提取最新的 session ID。

        会话结束后调用，用于记录 session_id 到 session.json。

        Args:
            workitem_dir: 工作项目录路径

        Returns:
            session ID 字符串，或 None（提取失败时）
        """

    @abstractmethod
    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否仍存在且可恢复。

        Args:
            session_id: 要验证的 session ID

        Returns:
            True 表示 session 存在且可恢复
        """

    @abstractmethod
    def sync_rules(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,
    ) -> None:
        """将 CLAUDE.md 同步到引擎原生的规则格式。

        Claude Code 自动加载 CLAUDE.md，此方法为空实现。
        OpenCode 需要生成 opencode.json 桥接配置，并可在此写入 model / provider 字段。

        Args:
            workitem_dir: 工作项目录路径
            model: 按回退链解析后的最终模型配置
        """

    def is_available(self) -> bool:
        """检查引擎是否可用（命令是否存在于 PATH）。

        Returns:
            True 表示引擎可执行文件存在
        """
        import shutil

        cmd = self._get_command()
        return shutil.which(cmd) is not None

    @abstractmethod
    def _get_command(self) -> str:
        """返回引擎的可执行命令名（如 "claude" / "opencode"）。"""
