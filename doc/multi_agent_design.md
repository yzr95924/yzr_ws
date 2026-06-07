# 多 Agent 引擎设计

## 概述

`yzrws` 不绑定特定的 Code Agent，而是通过**适配器模式**统一调度不同的 Agent 引擎。
当前主要适配两个引擎：

| 引擎 | 规则文件 | 恢复会话 | 非交互执行 |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`（约定式加载） | `claude --resume <id>` | `claude -p "prompt"` |
| OpenCode | `instructions` 数组（显式配置） | `opencode run -s <id>` | `opencode run "prompt"` |

核心原则：**CLAUDE.md 是唯一的项目规则源**，适配器负责将规则文件桥接到各引擎的配置格式。

## 架构

```text
yzrws (调度层)
  ├── engine/
  │     ├── base.py          # 引擎抽象基类
  │     ├── claude_code.py   # Claude Code 适配器
  │     └── opencode.py      # OpenCode 适配器
  └── workitem.py            # workitem 管理（读取 setting.json、session_id 等）
```

## 引擎抽象

所有 Agent 引擎实现统一的抽象接口：

```python
class AgentEngine(ABC):
    """Agent 引擎抽象基类。"""

    name: str  # 引擎标识：claude-code / opencode

    @abstractmethod
    def start(self, workitem_dir: Path) -> str:
        """启动新的交互式会话，返回 session_id。"""

    @abstractmethod
    def resume(self, workitem_dir: Path, session_id: str) -> str:
        """恢复指定会话，返回 session_id。"""

    @abstractmethod
    def run(self, workitem_dir: Path, prompt: str) -> str:
        """非交互执行，返回输出。"""

    @abstractmethod
    def sync_rules(self, workitem_dir: Path) -> None:
        """将 CLAUDE.md 同步到引擎原生的规则格式。"""

    @abstractmethod
    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否仍存在且可恢复。"""

    def save_session(self, workitem_dir: Path, session_id: str, **meta) -> None:
        """会话结束后写入 session.json（含 status / updated_at 等）。"""
        ...
```

> Session 元数据的完整结构、状态机和引擎切换流程见 [`session_design.md`](./session_design.md)。

## 适配器实现

### Claude Code 适配器

```python
class ClaudeCodeEngine(AgentEngine):
    name = "claude-code"

    def start(self, workitem_dir, *, model=None):
        cmd = self._get_command(model)         # 显式 --model / --base-url / --api-key
        env = self._build_env(model)           # ANTHROPIC_* 三件套
        subprocess.run(cmd, cwd=workitem_dir, env=env)

    def resume(self, workitem_dir, session_id, *, model=None):
        cmd = self._get_command(model) + ["--resume", session_id]
        env = self._build_env(model)
        subprocess.run(cmd, cwd=workitem_dir, env=env)

    def _get_command(self, model=None) -> list[str]:
        # 把 model / base_url / auth_key 全部用 CLI 标志显式追加——
        # CLI 参数优先级最高，覆盖 env 变量与 ~/.claude/settings.json 的同名配置
        cmd = ["claude"]
        if model is None:
            return cmd
        if model.model:
            cmd += ["--model", model.model]
        if model.base_url:
            cmd += ["--base-url", model.base_url]
        if model.auth_key:
            cmd += ["--api-key", model.auth_key]
        return cmd
```

**关键不变量**：Claude Code 的 API 连接参数来源有 3 层
（CLI 参数 > env > settings.json），yzrws **同时**在两层显式覆盖：

- **env 注入**：`_build_env` 把 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_MODEL` 写到 subprocess 环境
- **CLI 显式**：`_get_command` 把 `--base-url` / `--api-key` / `--model` 追加到
  `claude` 的 argv

仅 env 注入不够——`~/.claude/settings.json` 或项目级 `settings.json` 若
显式写这些字段，会反超 env（用户已踩过此坑：Model 解析对了，但 base URL
还是 settings.json 里的旧值）。CLI 参数优先级最高，**所有 3 个 API 连接
参数都覆盖**才能保证 yzrws 的解析结果一定生效，**不依赖**用户 / 项目配置。
字段为空时不追加对应 flag（避免给 Claude CLI 空串参数触发其解析错误）。

### OpenCode 适配器

```python
class OpenCodeEngine(AgentEngine):
    name = "opencode"

    def start(self, workitem_dir):
        self.sync_rules(workitem_dir)
        # opencode（在 workitem 目录下启动 TUI）
        ...

    def resume(self, workitem_dir):
        self.sync_rules(workitem_dir)
        session_id = self._read_session_id(workitem_dir)
        # opencode run -s <session_id>
        ...

    def run(self, workitem_dir, prompt):
        self.sync_rules(workitem_dir)
        # opencode run "prompt" --format json
        ...

    def sync_rules(self, workitem_dir):
        # 生成 opencode.json，instructions 指向 CLAUDE.md
        # 如果 opencode.json 已存在，只更新 instructions 字段
        ...

    def save_session_id(self, workitem_dir, session_id):
        # 写入 workitem_dir/session_id
        ...
```

### OpenCode 规则桥接

OpenCode 不像 Claude Code 那样约定式加载 `CLAUDE.md`，而是通过配置文件的 `instructions` 字段显式指定规则文件。
适配器在启动前自动生成 / 更新 `opencode.json`：

```jsonc
// <workitem>/opencode.json（自动生成，不纳入 git）
{
  "instructions": ["CLAUDE.md"],
  // 用户自定义配置通过 workitem 的 setting.json 合并
}
```

> `opencode.json` 是自动生成的桥接文件，加入 `.gitignore`。
> 用户的自定义配置（模型、MCP 等）放在 `setting.json` 中，由适配器在启动时合并。

## workitem 配置

### setting.json

每个 workitem 的 `setting.json` 新增 `engine` 字段，指定使用的 Agent 引擎：

```jsonc
{
  "engine": "claude-code",        // 引擎选择：claude-code / opencode
  "model": null,                  // 暂未由用户直接配置；运行时由 yzrws 按 `provider` 字段从 workspace provider.json 解析
  "provider": "anthropic",        // Provider 引用（由 `yzrws workitem set-model` 写入；null 表示继承 workspace 默认）
  "env": {}                       // 传递给引擎的额外环境变量
}
```

`provider` 字段由 `yzrws workitem set-model` 写入；未设置时按
[`provider_design.md §回退链`](./provider_design.md) 解析：workitem provider →
workspace `default` → 引擎内置默认。`yzrws start` 启动时按回退链加载
`(base_url, auth_key, model)`，分别注入到：

- **Claude Code**：`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` 环境变量
- **OpenCode**：`opencode.json` 的 `model` 与 `provider.<name>.{baseURL, apiKey}` 字段

> **engine 兼容性**：同一 model 名（如 `claude-sonnet-4-6`）可能出现在不同 Provider
> 中，但其 `base_url` 只适配特定 engine。Provider 配置中含 `agent_types` 字段
> （列表）用于标识支持的 engine 列表，缺省时表示兼容所有已注册 engine。
> `yzrws workitem set-model` 在选中的 provider 不兼容 workitem 当前 engine 时
> **报错**；`yzrws start` 在临时 `--engine` 切换到不兼容 engine 时仅 **WARN**。
> 详见 [`provider_design.md §Provider Schema`](./provider_design.md) 与 §场景五。

### 引擎选择策略

1. **workitem 级别**：`setting.json` 中的 `engine` 字段（最高优先级）
2. **兜底**：`claude-code`（来自 `commands/_create_workitem.py::DEFAULT_ENGINE`）

```sh
# 创建 workitem 时指定引擎
yzrws create workitem my-task --engine opencode

# 运行时临时切换引擎（不写回 setting.json）
yzrws start my-task --engine opencode
```

## 命令集成

### yzrws start

启动 workitem 的 Agent 会话（核心命令）：

```sh
# 启动（新会话）
yzrws start <workitem_name>

# 恢复（继续上次会话，未实现）
# yzrws start <workitem_name> --resume

# 指定引擎（覆盖 setting.json；当前 --engine 仅作用于自动创建 / 切换时的初始 engine）
yzrws start <workitem_name> --engine opencode
```

内部流程：

```text
1. 读取 <workitem>/setting.json，确定引擎
2. 读取 <workitem>/session_id（如果有）
3. 调用对应适配器的 sync_rules()
4. 调用 start() 或 resume()
5. 会话结束后，调用 save_session_id()
```

### yzrws run（未实现）

非交互执行（单次任务）—— 当前**尚未实现**，仅作为 `engine.run` 的设计占位：

```sh
# 计划中的用法：
# yzrws run <workitem_name> "帮我总结一下这个项目"
```

## Session 管理

会话元数据统一存放在结构化的 `session.json` 中（取代原设计的 `session_id` 文件）。
切换引擎时，当前会话归档到 `sessions/` 子目录，历史会话按引擎保留。

```text
<workitem>/
├── session.json                              # 当前活跃会话
└── sessions/                                 # 历史会话归档
    ├── claude-code_20260606T100000.json
    └── opencode_20260605T150000.json
```

> 完整的元数据结构、状态机、引擎切换流程和迁移兼容方案见 [`session_design.md`](./session_design.md)。

## 文件归属

| 文件 | 归属 | 是否纳入 git |
| --- | --- | --- |
| `CLAUDE.md` | 用户编写，唯一规则源 | ✓ |
| `setting.json` | 用户配置（引擎、模型等） | ✓ |
| `session.json` | 当前活跃会话元数据 | ✗ |
| `sessions/` | 历史会话归档 | ✗ |
| `opencode.json` | 自动生成，桥接规则 | ✗ |
| `workitem.json` | 元数据 | ✓ |
