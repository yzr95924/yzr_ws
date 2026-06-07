"""Claude Code 引擎适配器。

设计参考 doc/multi_agent_design.md §Claude Code 适配器 和 doc/session_design.md。

Claude Code 通过 ANTHROPIC_* 环境变量配置：
  - ANTHROPIC_BASE_URL   API 端点
  - ANTHROPIC_AUTH_TOKEN 认证密钥
  - ANTHROPIC_MODEL      模型名称
yzrws 在 start / resume 时把 ResolvedModel 注入到这 3 个环境变量。
"""

import os
import subprocess
from pathlib import Path

from yzrws.provider import ResolvedModel

from .base import AgentEngine


class ClaudeCodeEngine(AgentEngine):
    """Claude Code 引擎适配器。"""

    @property
    def name(self) -> str:
        return "claude-code"

    def start(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,
    ) -> int:
        """启动新的 Claude Code 会话。

        在 workitem_dir 下执行 claude 命令（交互式 TUI），
        继承父进程的 stdin/stdout/stderr 以支持交互。
        """
        cmd = self._get_command()
        env = self._build_env(model)
        result = subprocess.run(
            [cmd],
            cwd=workitem_dir,
            env=env,
            check=False,
        )
        return result.returncode

    def resume(
        self,
        workitem_dir: Path,
        session_id: str,
        *,
        model: ResolvedModel | None = None,
    ) -> int:
        """恢复指定会话。

        执行 claude --resume <session_id>。
        """
        cmd = self._get_command()
        env = self._build_env(model)
        result = subprocess.run(
            [cmd, "--resume", session_id],
            cwd=workitem_dir,
            env=env,
            check=False,
        )
        return result.returncode

    def extract_session_id(self, workitem_dir: Path) -> str | None:
        """从 ~/.claude/projects/ 提取最新的 session ID。

        Claude Code 将 session 存储在按项目路径编码的目录下。
        路径编码规则：/ 替换为 -（如 /Users/x/project → -Users-x-project）。
        每个 session 是一个 .jsonl 文件，文件名为 session ID。

        Returns:
            最新 session ID，或 None（提取失败时）
        """
        projects_dir = self._get_projects_dir()
        if projects_dir is None:
            return None

        # 查找与 workitem_dir 匹配的项目目录
        project_key = self._encode_path(workitem_dir)
        project_dir = projects_dir / project_key

        if not project_dir.is_dir():
            return None

        # 查找最新的 .jsonl 文件
        sessions = list(project_dir.glob("*.jsonl"))
        if not sessions:
            return None

        # 按修改时间排序，取最新
        sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        latest = sessions[0]

        # 文件名去掉 .jsonl 后缀即为 session ID
        return latest.stem

    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否存在。

        在 ~/.claude/projects/ 下查找对应的 .jsonl 文件。
        """
        projects_dir = self._get_projects_dir()
        if projects_dir is None:
            return False

        # 遍历所有项目目录查找 session
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                return True

        return False

    def sync_rules(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,  # noqa: ARG002
    ) -> None:
        """Claude Code 自动加载 CLAUDE.md，无需额外同步。

        model 参数在本适配器中不直接使用——配置通过 ANTHROPIC_* 环境变量注入。
        """
        # no-op

    def sync_mcp(
        self,
        workitem_dir: Path,
        mcp_config: dict | None,
    ) -> None:
        """把 MCP 配置写入 <workitem>/.mcp.json。

        mcp_config 非 None 时：原子写入 ``{"mcpServers": mcp_config}``。
        mcp_config 为 None 时：删除 .mcp.json（若存在），避免遗留敏感 token。
        """
        mcp_path = workitem_dir / ".mcp.json"

        if mcp_config is None:
            # 清理模式：删除桥接文件
            if mcp_path.is_file():
                mcp_path.unlink()
            return

        # 写入模式：原子写
        from yzrws.workspace import atomic_write_json

        payload = {"mcpServers": mcp_config}
        atomic_write_json(mcp_path, payload)

    def _get_command(self) -> str:
        return "claude"

    def _build_env(self, model: ResolvedModel | None) -> dict[str, str]:
        """构造 subprocess 环境变量，把 ResolvedModel 注入到 ANTHROPIC_*。

        model 为 None 或字段为 None 时，不覆盖对应环境变量。
        """
        env = os.environ.copy()
        if model is None:
            return env
        if model.base_url:
            env["ANTHROPIC_BASE_URL"] = model.base_url
        if model.auth_key:
            env["ANTHROPIC_AUTH_TOKEN"] = model.auth_key
        if model.model:
            env["ANTHROPIC_MODEL"] = model.model
        return env

    def _get_projects_dir(self) -> Path | None:
        """获取 Claude Code 的 projects 存储目录。"""
        claude_dir = Path.home() / ".claude"
        projects_dir = claude_dir / "projects"
        return projects_dir if projects_dir.is_dir() else None

    def _encode_path(self, path: Path) -> str:
        """将路径编码为 Claude Code 的项目目录名。

        规则：/ 替换为 -（如 /Users/x/project → -Users-x-project）。
        """
        # 转为绝对路径并规范化
        abs_path = path.resolve()
        # 将 / 替换为 -
        return str(abs_path).replace("/", "-")
