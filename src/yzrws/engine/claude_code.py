"""Claude Code 引擎适配器。

设计参考 doc/multi_agent_design.md §Claude Code 适配器 和 doc/session_design.md。

Claude Code 的 API 连接参数优先级（从高到低）：
  1. CLI 参数（仅 ``--model`` 是合法 CLI flag）
  2. 项目级 ``<workitem>/.claude/settings.json`` 的 ``env`` 块
  3. 用户级 ``~/.claude/settings.json`` 的 ``env`` 块
  4. ``ANTHROPIC_*`` 环境变量

⚠️  Claude CLI **没有** ``--base-url`` / ``--api-key`` CLI flag
（实测 ``--base-url`` 报 ``unknown option``），所以这俩只能走
settings.json 或 env——而 env 会被用户级 settings.json 的 env 块
反超。yzrws 在 ``sync_rules`` 阶段把 ``env`` 块写入项目级
settings.json，覆盖用户级同名 env，确保 base URL / auth token
一定生效；model 则**同时**走 ``--model`` CLI flag（最高优先级）
+ settings.json env 双保险。
"""

import os
import subprocess
from pathlib import Path

from yzrws.outline import OUTLINE_WRITE_TOOLS
from yzrws.provider import ResolvedModel

from .base import AgentEngine

# Outline MCP 写工具的 deny 条目（用于 read-only 模式注入到 settings.local.json）
_OUTLINE_DENY_ENTRIES = tuple(f"mcp__outline__{tool}" for tool in OUTLINE_WRITE_TOOLS)


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

        先把 yzrws 解析的 model 写入项目级 ``.claude/settings.json``
        （sync_rules），再执行 claude 命令（交互式 TUI），继承父进程
        的 stdin/stdout/stderr 以支持交互。``--model`` CLI flag 同时显式追加。
        """
        self.sync_rules(workitem_dir, model=model)
        cmd = self._get_command(model)
        env = self._build_env(model)
        result = subprocess.run(
            cmd,
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

        执行 claude --resume <session_id>。同样先 sync_rules，再 spawn。
        """
        self.sync_rules(workitem_dir, model=model)
        cmd = self._get_command(model)
        env = self._build_env(model)
        result = subprocess.run(
            cmd + ["--resume", session_id],
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
        model: ResolvedModel | None = None,
    ) -> None:
        """同步 yzrws 解析的 base URL / auth token / model 到项目级
        ``<workitem>/.claude/settings.json`` 的 env 块。

        **Why not only env injection**（与早期设计对比）：
        Claude Code 启动时按 user settings.json > env 的优先级解析
        API 连接参数——仅 subprocess env 注入会被 ``~/.claude/settings.json``
        的 env 块反超。所以 yzrws 把 env 写入**项目级** settings.json，
        项目级 env 优先级**高于**用户级，确保 yzrws 解析结果一定生效。
        （同时 ``--model`` CLI flag 也会传，但只覆盖 model 字段。）

        **Why not overwrite unrelated fields**：
        读取已有项目级 settings.json，仅 merge ``env`` 块；其他字段
        （如用户自定义 ``permissions`` / ``cleanupPeriodDays`` 等）原样保留。
        """
        if model is None:
            return
        if not (model.base_url or model.auth_key or model.model):
            return

        import json

        from yzrws.workspace import atomic_write_json

        claude_dir = workitem_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings_path = claude_dir / "settings.json"

        # 读取已有配置，merge env 块（保留用户自定义字段）
        config: dict = {}
        if settings_path.is_file():
            try:
                config = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}

        env_block = config.get("env")
        if not isinstance(env_block, dict):
            env_block = {}

        if model.base_url:
            env_block["ANTHROPIC_BASE_URL"] = model.base_url
        if model.auth_key:
            env_block["ANTHROPIC_AUTH_TOKEN"] = model.auth_key
        if model.model:
            env_block["ANTHROPIC_MODEL"] = model.model
        config["env"] = env_block

        atomic_write_json(settings_path, config)

    def sync_mcp(
        self,
        workitem_dir: Path,
        mcp_config: dict | None,
        *,
        read_only: bool = False,
    ) -> None:
        """把 MCP 配置写入 <workitem>/.mcp.json。

        mcp_config 非 None 时：原子写入 ``{"mcpServers": mcp_config}``，
        并按 ``read_only`` 标志同步 ``.claude/settings.local.json`` 的
        Outline 写工具 deny 条目（详见 §_sync_outline_permissions）。
        mcp_config 为 None 时：删除 .mcp.json（若存在），避免遗留敏感 token；
        同时清除残留的 deny 条目。
        """
        mcp_path = workitem_dir / ".mcp.json"

        if mcp_config is None:
            # 清理模式：删除桥接文件 + 清除残留权限
            if mcp_path.is_file():
                mcp_path.unlink()
            self._sync_outline_permissions(workitem_dir, read_only=False)
            return

        # 写入模式：原子写
        from yzrws.workspace import atomic_write_json

        payload = {"mcpServers": mcp_config}
        atomic_write_json(mcp_path, payload)

        # 同步 read-only 权限到 settings.local.json
        self._sync_outline_permissions(workitem_dir, read_only=read_only)

    def _sync_outline_permissions(self, workitem_dir: Path, read_only: bool) -> None:
        """管理 ``<workitem>/.claude/settings.local.json`` 中 Outline
        写工具的 deny 条目。

        采用"外科手术式"合并策略：仅增删 ``OUTLINE_WRITE_TOOLS`` 对应的
        deny 条目，不触碰用户自定义的其他权限（allow / deny 均原样保留）。

        Args:
            workitem_dir: 工作项目录
            read_only: True 时添加 deny 条目；False 时移除
        """
        import json

        from yzrws.workspace import atomic_write_json

        settings_local_path = workitem_dir / ".claude" / "settings.local.json"

        # 读取已有配置
        config: dict = {}
        if settings_local_path.is_file():
            try:
                config = json.loads(settings_local_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}
        if not isinstance(config, dict):
            config = {}

        deny_set = frozenset(_OUTLINE_DENY_ENTRIES)

        # 从 permissions.deny 中过滤掉已知的 Outline 写工具条目
        permissions = config.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}

        deny = permissions.get("deny")
        if not isinstance(deny, list):
            deny = []

        deny = [entry for entry in deny if entry not in deny_set]

        # read_only 模式：重新添加 deny 条目
        if read_only:
            deny.extend(_OUTLINE_DENY_ENTRIES)

        # 回写 permissions
        if deny:
            permissions["deny"] = deny
        else:
            permissions.pop("deny", None)

        if permissions:
            config["permissions"] = permissions
        else:
            config.pop("permissions", None)

        # 原子写回（确保 .claude 目录存在）
        claude_dir = workitem_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(settings_local_path, config)

    def _get_command(self, model: ResolvedModel | None = None) -> list[str]:
        """构造 claude 命令行参数列表。

        仅 ``--model`` 是合法的 Claude CLI flag（``--base-url`` /
        ``--api-key`` 实测都是 ``unknown option``）。其它两个
        API 连接参数（base URL / auth token）走 sync_rules 写
        项目级 ``.claude/settings.json`` 的 env 块，详见
        doc/multi_agent_design.md §Claude Code 适配器。

        ``model.model`` 空时不追加 ``--model``，让 Claude CLI 走自己默认。
        """
        if model is not None and model.model:
            return ["claude", "--model", model.model]
        return ["claude"]

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
