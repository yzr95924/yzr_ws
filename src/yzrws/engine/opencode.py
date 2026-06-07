"""OpenCode 引擎适配器。

设计参考 doc/multi_agent_design.md §OpenCode 适配器 和 doc/session_design.md。

OpenCode 通过 opencode.json 配置：
  - instructions    规则文件数组（桥接 CLAUDE.md）
  - model           模型名称
  - provider.<name> 服务商配置（含 baseURL / apiKey）
yzrws 在 sync_rules 时把 ResolvedModel 写入 opencode.json。
"""

import json
import subprocess
from pathlib import Path

from yzrws.provider import ResolvedModel
from yzrws.workspace import atomic_write_json

from .base import AgentEngine

# OpenCode 配置文件名
_OPENCODE_CONFIG = "opencode.json"


class OpenCodeEngine(AgentEngine):
    """OpenCode 引擎适配器。"""

    @property
    def name(self) -> str:
        return "opencode"

    def start(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,
    ) -> int:
        """启动新的 OpenCode 会话。

        先同步规则文件（opencode.json 包含 model / provider 块），
        然后在 workitem_dir 下执行 opencode 命令。

        OpenCode 不接受 CLI 上的 model 标志（model 由 opencode.json
        提供，yzrws 在 sync_rules 阶段写入），所以 _get_command 直接
        返回 ``["opencode"]``。
        """
        self.sync_rules(workitem_dir, model=model)

        cmd = self._get_command(model)
        result = subprocess.run(
            cmd,
            cwd=workitem_dir,
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

        执行 opencode run -s <session_id>。
        """
        self.sync_rules(workitem_dir, model=model)

        cmd = self._get_command(model)
        result = subprocess.run(
            cmd + ["run", "-s", session_id],
            cwd=workitem_dir,
            check=False,
        )
        return result.returncode

    def extract_session_id(self, workitem_dir: Path) -> str | None:
        """从 opencode session list 提取最新的 session ID。

        执行 opencode session list 并解析 JSON 输出。

        Returns:
            最新 session ID，或 None（提取失败时）
        """
        cmd = self._get_command()
        try:
            result = subprocess.run(
                cmd + ["session", "list", "--json"],
                cwd=workitem_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None

        try:
            sessions = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

        if not isinstance(sessions, list) or not sessions:
            return None

        # 按 created_at 或 id 排序，取最新
        # OpenCode session list 输出格式可能包含 id、title、created_at 等字段
        # 尝试多种排序策略
        def sort_key(s: dict) -> str:
            return s.get("created_at", "") or s.get("id", "")

        sessions.sort(key=sort_key, reverse=True)
        latest = sessions[0]

        # 提取 session ID（可能是 "id" 或 "session_id" 字段）
        return latest.get("id") or latest.get("session_id")

    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否存在。

        通过 opencode session list 查找。
        """
        cmd = self._get_command()
        try:
            result = subprocess.run(
                cmd + ["session", "list", "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False

        if result.returncode != 0:
            return False

        try:
            sessions = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False

        if not isinstance(sessions, list):
            return False

        # 查找匹配的 session ID
        for s in sessions:
            sid = s.get("id") or s.get("session_id")
            if sid == session_id:
                return True

        return False

    def sync_rules(
        self,
        workitem_dir: Path,
        *,
        model: ResolvedModel | None = None,
    ) -> None:
        """生成 / 更新 opencode.json。

        字段：
          - instructions: 桥接 CLAUDE.md 的规则文件列表
          - model: 当前生效的模型名称（model 非 None 时写入）
          - provider.<name>.{baseURL, apiKey}: 当前生效的 Provider 配置
            （model 非 None 且 baseURL / apiKey 非 None 时写入）
        """
        config_path = workitem_dir / _OPENCODE_CONFIG

        # 读取现有配置（如果有）
        config: dict = {}
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}

        # 确保 instructions 包含 CLAUDE.md
        instructions = config.get("instructions", [])
        if not isinstance(instructions, list):
            instructions = []
        claude_md = "CLAUDE.md"
        if claude_md not in instructions:
            instructions.insert(0, claude_md)
        config["instructions"] = instructions

        # 写入 model（如果已解析）
        if model is not None and model.model:
            config["model"] = model.model

            # 写入 provider.<name> 块
            if model.provider_name:
                providers = config.get("provider")
                if not isinstance(providers, dict):
                    providers = {}
                provider_block: dict = {}
                if model.base_url:
                    provider_block["baseURL"] = model.base_url
                if model.auth_key:
                    provider_block["apiKey"] = model.auth_key
                if provider_block:
                    providers[model.provider_name] = provider_block
                config["provider"] = providers

        # 原子写入
        atomic_write_json(config_path, config)

    def sync_mcp(
        self,
        workitem_dir: Path,
        mcp_config: dict | None,
    ) -> None:
        """把 MCP 配置合并到 opencode.json 的 ``mcp`` 字段。

        mcp_config 非 None 时：读取现有 opencode.json，把每个 server entry
        的 type 从 ``http`` 映射为 ``remote``（OpenCode 约定），写入 ``mcp``
        字段，原子写回。
        mcp_config 为 None 时：从 opencode.json 移除 ``mcp.outline`` 字段
        （保留用户自定义的其他 MCP 配置）。
        """
        config_path = workitem_dir / _OPENCODE_CONFIG

        # 读取现有配置
        config: dict = {}
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}

        if mcp_config is None:
            # 清理模式：移除 mcp.outline
            mcp_block = config.get("mcp")
            if isinstance(mcp_block, dict) and "outline" in mcp_block:
                del mcp_block["outline"]
                if not mcp_block:
                    # mcp 字段为空，整体移除
                    config.pop("mcp", None)
                else:
                    config["mcp"] = mcp_block
        else:
            # 写入模式：合并 mcp 字段（type: http → remote）
            mcp_block = config.get("mcp")
            if not isinstance(mcp_block, dict):
                mcp_block = {}
            for server_name, server_cfg in mcp_config.items():
                translated = dict(server_cfg)
                if translated.get("type") == "http":
                    translated["type"] = "remote"
                mcp_block[server_name] = translated
            config["mcp"] = mcp_block

        # 原子写回
        atomic_write_json(config_path, config)

    def _get_command(self, model: ResolvedModel | None = None) -> list[str]:
        """OpenCode 不接受 CLI model 标志（model 由 opencode.json 提供）；
        为对齐抽象接口签名仍接受 ``model`` 参数但不使用。
        """
        return ["opencode"]
