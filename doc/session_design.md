# Session 管理设计

## 概述

每个 workitem 绑定一个可恢复的 Code Agent Session，支持断点续传。
由于不同引擎的 session 机制存在差异，`yzrws` 需要在调度层做统一抽象，
同时保留各引擎的原生能力。

本文档是 [`multi_agent_design.md`](./multi_agent_design.md) 中 session 相关设计的细化。

> **未实现的命令**：本文档中提到的 `yzrws start <workitem> --resume` / `yzrws archive`
> 等命令**尚未实现**；当前 `yzrws start` 的恢复能力由引擎适配器（`engine.resume`）
> 在 `session_id` 存在时自动调用承担，yzrws 层仅暴露 `--new` 强制新建。
> 详细命令清单见 [`command_design.md`](./command_design.md)。

## Session 元数据（session.json）

原设计中 workitem 目录下使用简单的 `session_id` 文件保存会话 ID。
随着多引擎支持和更丰富的状态管理需求，升级为结构化的 `session.json`：

```jsonc
// <workitem>/session.json（运行时文件，不纳入 git）
{
  "engine": "claude-code",            // 当前活跃的引擎
  "session_id": "abc123",             // 引擎原生的 session id
  "status": "active",                 // 会话状态（见状态机）
  "model": "claude-sonnet-4-6",       // 当前会话使用的模型
  "provider": "anthropic",            // Provider 引用
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T11:30:00Z",
  "resume_count": 3                   // 恢复次数（用于诊断）
}
```

> `session.json` 取代原设计中的 `session_id` 文件。
> 旧的 `session_id` 文件在迁移时自动转换为 `session.json`。

## 会话状态机

```text
                 ┌──────────────────────┐
                 │                      ▼
  (new) ──► active ──► paused ──► completed ──► archived
               ▲          │
               └──────────┘
               (resume)
```

| 状态 | 含义 | 进入条件 |
| --- | --- | --- |
| `active` | 会话正在进行 | `yzrws start` 启动 / `--resume` 恢复 |
| `paused` | 会话已暂停，可恢复 | Agent 正常退出 / 用户手动暂停 |
| `completed` | 会话已完成 | 用户标记完成 / Agent 报告任务结束 |
| `archived` | 会话已归档 | `yzrws archive` 归档 / 超过保留期限 |

## 各引擎 Session 机制对比

| 能力 | Claude Code | OpenCode |
| --- | --- | --- |
| session 存储位置 | `~/.claude/projects/` 下按项目路径索引 | OpenCode 内部数据库 |
| 恢复命令 | `claude --resume <id>` | `opencode run -s <id>` |
| 恢复上次 | `claude --resume`（无参数） | `opencode run -c` |
| 会话列表 | 无原生 CLI | `opencode session list` |
| 会话导出 | 不支持 | `opencode export` |
| 会话导入 | 不支持 | `opencode import` |
| 会话分叉 | 不支持 | `opencode run --fork <id>` |
| session 可移植性 | ✗（绑定本机 + 项目路径） | ✓（export / import） |
| session 过期 | 无明确过期机制 | 无明确过期机制 |

## 适配器 Session 处理

### Claude Code

```python
class ClaudeCodeEngine(AgentEngine):

    def start(self, workitem_dir: Path) -> str:
        """启动新会话，返回 session_id。"""
        # 1. cd 到 workitem_dir
        # 2. 执行 claude（交互式 TUI）
        # 3. 退出后从 ~/.claude/projects/ 提取最新 session_id
        # 4. 返回 session_id
        ...

    def resume(self, workitem_dir: Path, session_id: str) -> str:
        """恢复指定会话。"""
        # 1. cd 到 workitem_dir
        # 2. 执行 claude --resume <session_id>
        # 3. session_id 不变（Claude Code 复用同一个 id）
        # 4. 返回 session_id
        ...

    def extract_session_id(self) -> str:
        """从 Claude Code 本地存储提取最新 session_id。"""
        # 读取 ~/.claude/projects/<encoded_path>/ 下最新的 session 文件
        ...

    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否仍存在且可恢复。"""
        # 检查 ~/.claude/projects/ 下对应 session 文件是否存在
        ...
```

**关键约束：**

- Claude Code 的 session_id 与**项目路径强绑定**——workitem 目录移动后旧 session 失效
- 恢复时若 session 已失效，提示用户新建会话

### OpenCode

```python
class OpenCodeEngine(AgentEngine):

    def start(self, workitem_dir: Path) -> str:
        """启动新会话，返回 session_id。"""
        # 1. sync_rules() 生成 opencode.json
        # 2. cd 到 workitem_dir
        # 3. 执行 opencode（交互式 TUI）
        # 4. 退出后通过 opencode session list 提取最新 session_id
        # 5. 返回 session_id
        ...

    def resume(self, workitem_dir: Path, session_id: str) -> str:
        """恢复指定会话。"""
        # 1. sync_rules()
        # 2. 执行 opencode run -s <session_id>
        # 3. 返回 session_id
        ...

    def fork(self, workitem_dir: Path, session_id: str) -> str:
        """从现有会话分叉一个新会话（OpenCode 特有能力）。"""
        # 执行 opencode run --fork <session_id> "prompt"
        # 返回新的 session_id
        ...

    def export_session(self, session_id: str, output_path: Path) -> None:
        """导出会话记录（OpenCode 特有能力）。"""
        # 执行 opencode export -s <session_id> -o <output_path>
        ...

    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否存在。"""
        # 通过 opencode session list 查找
        ...
```

**特有能力：**

- `fork`：从现有会话分叉出新分支，适合"试错"场景
- `export` / `import`：会话可跨机器迁移，适合 workitem 导入 / 导出场景

## Session 生命周期

### 启动新会话

```text
yzrws start <workitem>
  │
  ├── 1. 读取 setting.json，确定引擎
  ├── 2. 检查是否存在 session.json
  │     ├── 存在且 status=active/paused → 提示用户：恢复 or 新建
  │     └── 不存在 / status=completed → 继续新建
  ├── 3. 调用 engine.start(workitem_dir)
  ├── 4. 获取返回的 session_id
  ├── 5. 写入 session.json（status=active）
  └── 6. 会话退出后更新 session.json（status=paused, updated_at）
```

### 恢复会话

```text
yzrws start <workitem> --resume
  │
  ├── 1. 读取 session.json
  │     ├── 不存在 → 报错：无可恢复的会话
  │     └── 存在 → 继续
  ├── 2. 检查 session.json.engine 与 setting.json.engine 是否匹配
  │     ├── 匹配 → 继续
  │     └── 不匹配 → 进入引擎切换流程（见下文）
  ├── 3. 调用 engine.validate_session(session_id)
  │     ├── 有效 → 继续
  │     └── 失效 → 提示用户：session 已失效，是否新建
  ├── 4. 调用 engine.resume(workitem_dir, session_id)
  ├── 5. 更新 session.json（status=active, resume_count++）
  └── 6. 会话退出后更新 session.json（status=paused, updated_at）
```

### 会话结束

Agent 退出后，适配器根据退出码更新状态：

| 退出码 | 更新为 | 含义 |
| --- | --- | --- |
| 0 | `paused` | 正常退出，可恢复 |
| 非 0 | `paused` | 异常退出，仍可尝试恢复 |
| 用户标记 | `completed` | 任务完成，不再恢复 |

## 引擎切换流程

当 `session.json.engine` 与 `setting.json.engine` 不匹配时：

```text
当前 session.json: { engine: "claude-code", session_id: "abc" }
用户切换为:        setting.json: { engine: "opencode" }

yzrws start <workitem> --resume
  │
  ├── 检测到引擎不匹配
  │
  ├── 1. 将当前 session.json 归档到 sessions/ 目录
  │     └── sessions/claude-code_20260606T113000.json
  │
  ├── 2. 检查目标引擎是否有历史会话
  │     ├── sessions/opencode_*.json 存在
  │     │     └── 提示用户：恢复历史 OpenCode 会话 or 新建
  │     └── 不存在
  │           └── 提示用户：新建 OpenCode 会话
  │
  └── 3. 根据用户选择执行 resume / start
```

### 历史会话归档目录

```text
<workitem>/
├── session.json                              # 当前活跃会话
└── sessions/                                 # 历史会话归档
    ├── claude-code_20260606T100000.json       # 按 {engine}_{timestamp}.json 命名
    ├── opencode_20260605T150000.json
    └── claude-code_20260604T090000.json
```

归档文件格式与 `session.json` 相同，额外增加 `archived_at` 字段：

```jsonc
{
  "engine": "claude-code",
  "session_id": "abc123",
  "status": "archived",
  "model": "claude-sonnet-4-6",
  "provider": "anthropic",
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T11:30:00Z",
  "archived_at": "2026-06-06T12:00:00Z",   // 归档时间
  "resume_count": 3
}
```

## 迁移兼容

从旧的 `session_id` 文件迁移到 `session.json`：

```python
def migrate_legacy_session(workitem_dir: Path) -> None:
    """如果存在旧的 session_id 文件，迁移为 session.json。"""
    session_id_file = workitem_dir / "session_id"
    if not session_id_file.exists():
        return

    session_id = session_id_file.read_text().strip()
    engine = _detect_engine_from_setting(workitem_dir)

    session_json = {
        "engine": engine,
        "session_id": session_id,
        "status": "paused",         # 旧文件无法确认状态，默认 paused
        "model": None,
        "provider": None,
        "created_at": None,         # 旧文件无时间信息
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "resume_count": 0,
    }

    (workitem_dir / "session.json").write_text(json.dumps(session_json, indent=2))
    session_id_file.unlink()  # 删除旧文件

    # 同时清理引擎后缀格式的旧文件
    for suffix_file in workitem_dir.glob("session_id.*"):
        suffix_file.unlink()
```

## 文件归属总结

| 文件 | 说明 | 纳入 git |
| --- | --- | --- |
| `session.json` | 当前活跃会话元数据 | ✗ |
| `sessions/` | 历史会话归档目录 | ✗ |
| `session_id`（旧） | 迁移前的遗留文件 | ✗ |
| `workitem.json` | workitem 元数据（name / status 等） | ✓ |
| `setting.json` | 用户配置（引擎、模型等） | ✓ |

## 与 multi_agent_design.md 的关系

- 本文档细化了 `multi_agent_design.md` 中 `save_session_id()` 接口的内部逻辑
- `AgentEngine` 抽象基类中的 `save_session_id()` 实际写入的是 `session.json`（而非简单文件）
- `validate_session()` 和 `fork()` 是后续新增的接口，需同步更新 `multi_agent_design.md`
