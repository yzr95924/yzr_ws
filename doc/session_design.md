# Session 管理设计

## 概述

每个 workitem 下可有多个用户命名的 Code Agent Session，支持断点续传。
不同引擎的 session 机制存在差异，`yzrws` 在调度层做统一抽象，同时保留
各引擎的原生能力。

本文档是 [`multi_agent_design.md`](./multi_agent_design.md) 中 session 相关设计的细化。

## 存储布局

多 session 设计的核心：把"当前活跃 session 的完整元数据"和"workitem 下的
session 列表"分开。

```text
<workitem>/
├── session.json                          # 指针：{"current": "<name>"}
└── sessions/
    ├── default.json                      # 用户命名 session
    ├── explore-outline.json
    ├── fix-bug-2026-06.json
    └── _archive_claude-code_20260606T154440.json   # 引擎切换自动归档
```

约定：

- `session.json` 仅含 `current` 字段（小文件，原子写）
- `sessions/<name>.json` 是每个用户命名 session 的完整元数据
- 下划线前缀 `_archive_*` 的文件是引擎切换自动归档，**不**参与 `list` /
  `use` / `remove` 等用户操作
- session 名规则：1-32 字符，小写字母 / 数字开头，可含 `-_`（与 Provider
  名规则一致；详见 `src/yzrws/commands/_name.py`）

## Session 元数据（sessions/[name].json）

```jsonc
{
  "name": "default",                  // 与文件名一致（保留以便迁移兼容）
  "engine": "claude-code",            // 引擎（决定 resume 命令）
  "session_id": "abc123",             // 引擎原生 session id
  "status": "paused",                 // active / paused / completed / archived
  "title": "默认会话",                  // 用户给的备注
  "model": "claude-sonnet-4-6",       // 当前会话使用的模型
  "provider": "anthropic",            // Provider 引用
  "created_at": "2026-06-06T10:00:00+08:00",
  "updated_at": "2026-06-06T11:30:00+08:00",
  "resume_count": 3                   // 恢复次数（用于诊断）
}
```

`status` 取值含义：

| 状态 | 含义 | 进入条件 |
| --- | --- | --- |
| `active` | 会话正在进行 | `yzrws start` 启动 / `--session` 恢复 |
| `paused` | 会话已暂停，可恢复 | Agent 正常退出 / 用户手动暂停 |
| `completed` | 会话已完成 | 用户标记完成 / Agent 报告任务结束 |
| `archived` | 会话已归档 | 引擎切换自动触发，写入 `_archive_*` |
| `removed` | （未使用；删除走 `delete_session_by_name`） | — |

> 历史迁移：旧 `session.json`（无 `current` 字段、含 `engine / session_id`
> 等）会自动迁移到 `sessions/default.json` + 指针；旧
> `sessions/<engine>_<timestamp>.json` 自动重命名为 `_archive_*`。
> 迁移函数 `migrate_legacy_session` 幂等，详见 §迁移兼容。

## Current 指针（session.json）

`session.json` 是 2 字段的小文件，**仅**作指针：

```jsonc
{
  "current": "default"   // 或 null（指针清空）
}
```

读 / 写 API：

- `get_current_session_name(workitem_dir) -> str | None` — 读 current；空 / 缺失 / 解析失败返回 None
- `set_current_session_name(workitem_dir, name | None) -> None` — 原子写指针

> 用单独的指针文件而非把 current 嵌在某个 session 文件里，是为了避免
> "切 current 时要改两个文件"的非原子问题；`session.json` 单一原子写
> 即可。

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

    def start(self, workitem_dir: Path) -> int:
        """启动新会话，返回退出码。"""
        ...

    def resume(self, workitem_dir: Path, session_id: str) -> int:
        """恢复指定会话。"""
        ...

    def extract_session_id(self, workitem_dir: Path) -> str | None:
        """从 ~/.claude/projects/<encoded_path>/ 提取最新 session_id。"""
        ...

    def validate_session(self, session_id: str) -> bool:
        """检查 session 是否仍存在且可恢复。"""
        ...
```

**关键约束：**

- Claude Code 的 session_id 与**项目路径强绑定**——workitem 目录移动后旧 session 失效
- 恢复时若 session 已失效，提示用户新建会话

### OpenCode

```python
class OpenCodeEngine(AgentEngine):

    def start(self, workitem_dir: Path) -> int:
        ...

    def resume(self, workitem_dir: Path, session_id: str) -> int:
        ...

    def fork(self, workitem_dir: Path, session_id: str) -> str:
        """从现有会话分叉一个新会话。"""
        ...

    def export_session(self, session_id: str, output_path: Path) -> None:
        ...

    def validate_session(self, session_id: str) -> bool:
        ...
```

**特有能力：**

- `fork`：从现有会话分叉出新分支，适合"试错"场景
- `export` / `import`：会话可跨机器迁移

## Session 生命周期

### 启动新会话（yzrws start workitem）

```text
yzrws start <workitem> [--session <name>] [--title "<text>"]
  │
  ├── 1. 读 setting.json，确定 engine_name
  ├── 2. ★ 迁移旧格式（migrate_legacy_session，幂等）
  ├── 3. 决定 target session 名
  │     - --session 给定 → 用其值
  │     - 缺省 → 读 current 指针；current 为空则用 "default"
  ├── 4. 读 sessions/<name>.json（可能 None = 新建场景）
  ├── 5. ★ 引擎冲突检测：target_session.engine ≠ engine_name → error
  ├── 6. 启动引擎：session 存在 → resume；不存在 → start
  ├── 7. 写回 sessions/<name>.json（resume 续命 / start 新建）
  └── 8. 更新 session.json 指针（若与原 current 不同则提示）
```

### 场景分支

| current | `--session` | `sessions/<n>.json` | 行为 |
| --- | --- | --- | --- |
| 不存在 | 未给 | 任意 | 创建 `default`（title 缺省） |
| "x" | 未给 | 存在 | 续命 x；current 不变 |
| "x" | "y" (≠x) | 存在 | 续命 y；切 current → y |
| "x" | "y" (≠x) | 不存在 | 创建 y；切 current → y |
| "x" | "y" (≠x) | y.engine ≠ engine_name | **error**（避免"归档 X"的歧义） |

### 引擎冲突

`--engine` 与现存 `session.engine` 不一致时 error（避免 start 流程里
"归档 X" 行为的歧义），提示用户：

- 去掉 `--engine`，沿用 session 自带的 engine
- 切换 `--engine` 到与 `session.engine` 一致
- 删除该 session 后用同名新建

实现见 `src/yzrws/output.py::print_session_engine_mismatch`。

### 引擎切换（隐式）

`archive_session` 仅在以下场景被调用：

- 旧版 `start` 的引擎切换归档（迁移期兼容）
- 未来需要按 session 归档时（**当前不自动触发**，见 §引擎冲突）

归档命名：`sessions/_archive_<engine>_<timestamp>.json`（下划线前缀确保不
与用户命名 session 冲突）。

### 会话结束

Agent 退出后，适配器根据退出码更新 status：

| 退出码 | 更新为 | 含义 |
| --- | --- | --- |
| 0 | `paused` | 正常退出，可恢复 |
| 非 0 | `paused` | 异常退出，仍可尝试恢复 |
| 用户标记 | `completed` | 任务完成，不再恢复 |

## 管理多 Session 的命令

完整命令清单见 [`command_design.md`](./command_design.md) §管理 session。
简表：

| 命令 | 行为 |
| --- | --- |
| `yzrws workitem session list <workitem>` | 列出所有用户命名 session，标注 current |
| `yzrws workitem session show <workitem> <session>` | 显示 session 详情 |
| `yzrws workitem session remove <workitem> <session> [-y]` | 删除 session 元数据；删 current 时清空指针 |
| `yzrws workitem session use <workitem> <session>` | 切换 current 指针 |
| `yzrws start <workitem> --session <name> [--title "..."]` | start 时指定 session |

## 迁移兼容

旧格式（单 session）到新格式（多 session）的迁移函数
`migrate_legacy_session(workitem_dir)` 幂等，自动在以下入口触发：

- `yzrws start <workitem>` 入口
- `yzrws workitem session *` 任意子命令入口（在 `_precheck_session_target` 中）

迁移规则：

1. **旧 `session.json`**（含 `engine / session_id` 等字段，无 `current` 键）
   - 搬到 `sessions/default.json`（若已存在同名，加 timestamp 后缀避免覆盖）
   - 改写 `session.json` 为 `{"current": "default"}`
2. **旧 `sessions/<engine>_<timestamp>.json`**（引擎切换归档，**无下划线前缀**）
   - 重命名为 `sessions/_archive_<engine>_<timestamp>.json`（已有同名则跳过）
3. **JSON 损坏**：保守写 `{"current": null}`，让 start 时按 `default` 创建
4. **新格式下**：直接 return，可重复调用

```python
def migrate_legacy_session(workitem_dir: Path) -> None:
    # 0) 旧归档重命名（先做这一步，下面的 1/2 才不会把旧归档误读）
    for p in sessions_root.glob("*.json"):
        if p.stem.startswith(_ARCHIVE_PREFIX):
            continue
        if "_" not in p.stem:
            continue
        head = p.stem.split("_", 1)[0]
        if head not in {"claude-code", "opencode"}:
            continue
        new_path = p.with_name(f"_archive_{p.name}")
        if not new_path.exists():
            p.rename(new_path)

    # 1) 旧 session.json → sessions/default.json + 指针
    if session_path.is_file():
        if "current" in data:
            return  # 新格式，无需迁移
        atomic_write_json(sessions/default.json, data)
        atomic_write_json(session_path, {"current": "default"})

    # 2) session.json 缺失但有 _archive_<engine>_<ts>.json：还原最新一份为 default
    latest = max(_archive_*.json, key=mtime)
    atomic_write_json(sessions/default.json, json.load(latest))
    atomic_write_json(session_path, {"current": "default"})
```

## 文件归属总结

| 文件 | 说明 | 纳入 git |
| --- | --- | --- |
| `session.json` | current 指针（`{"current": "<name>"}`） | ✗ |
| `sessions/<name>.json` | 用户命名 session 元数据 | ✗ |
| `sessions/_archive_*.json` | 引擎切换自动归档 | ✗ |
| `workitem.json` | workitem 元数据（name / status 等） | ✓ |
| `setting.json` | 用户配置（引擎、模型等） | ✓ |

## 已知限制

`engine.extract_session_id` 通过 `~/.claude/projects/<encoded>/` 下"最新
`.jsonl`"推断 session_id。多 session 并存 + 短时间交替启动时，mtime 顺序
可能与 TUI 退出顺序不一致，导致 start 新 session 时拿到的 session_id 是
别的 session。**短期接受**；中期方案是 start 前后记录 mtime 基准 + 过滤
（本计划不做）。

## 与 multi_agent_design.md 的关系

- 本文档细化了 `multi_agent_design.md` 中 `save_session_id()` 接口的内部逻辑
- `AgentEngine` 抽象基类中的 `save_session_id()` 实际写入的是
  `sessions/<name>.json`（不再是单一 `session.json`）
- `validate_session()` / `fork()` 等接口由引擎适配器实现
