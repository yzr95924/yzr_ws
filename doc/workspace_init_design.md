# Workspace 初始化设计

## 概述

`yzrws init` 是 `yzrws` 工具的第一步命令，负责在本地创建并初始化 workspace 目录结构。
workspace 是 `yzrws` 的运行时根目录（默认 `~/yzr_workspace`），承载所有工作项、
全局知识库和跨工作项记忆。

初始化不只是 `mkdir -p`——它需要保证目录结构完整、元数据文件内容正确、
多次执行保持幂等，并在已有 workspace 上执行时提供自检报告。

## 场景分析

### 场景一：全新初始化

**触发条件**：用户首次使用 `yzrws`，workspace 目录不存在。

**期望行为**：创建完整的目录结构和全部初始文件，用户后续可直接执行 `yzrws create workitem`。

**困难与挑战**：

- 初始文件需要写入合理的默认内容（不能是空文件），否则后续命令读取时会报错
- `metadata.json` 的 schema 需要在此刻定义，且要预留版本字段以支持未来升级

### 场景二：部分存在

**触发条件**：workspace 目录已存在，但缺少部分子目录或文件（如用户手动删除了某个文件，
或从旧版本升级）。

**期望行为**：检测缺失项，只补充缺失的目录和文件，不覆盖已有内容。

**困难与挑战**：

- 需要区分"目录存在但文件缺失"和"文件存在但内容损坏"两种情况
- 已有的 `MEMORY.md` 可能包含用户数据，绝对不能覆盖
- `metadata.json` 可能存在但 schema 版本过旧，需要兼容处理

### 场景三：幂等重跑

**触发条件**：workspace 已完整初始化，用户再次执行 `yzrws init`。

**期望行为**：不报错、不修改任何文件，输出"workspace 已就绪"和自检报告。

**困难与挑战**：

- 自检逻辑需要快速执行（workspace 完整时不应有明显延迟）
- 输出信息要有用——不只是"OK"，还要列出检查了哪些项

### 场景四：目标路径被占用

**触发条件**：workspace 路径已存在但不是目录（如是文件），或当前用户无写权限。

**期望行为**：给出清晰的错误提示，不做任何修改。

**困难与挑战**：

- 需要在创建前检测路径类型和权限，区分不同的失败原因
- 错误信息需要可操作——告诉用户"怎么解决"而不只是"失败了"

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 全新初始化 | 目录不存在 | 初始文件默认内容定义 | §初始化流程 / §初始内容 |
| 部分存在 | 目录存在但不完整 | 补全而不覆盖已有数据 | §自检逻辑 |
| 幂等重跑 | 目录完整 | 快速自检 + 有意义的输出 | §自检逻辑 |
| 目标路径被占用 | 路径非目录 / 无权限 | 可操作的错误提示 | §命令接口 |

## 方案选择

### 备选方案

#### 方案 A：纯目录创建

仅执行 `mkdir -p` 创建目录树，不写入任何初始文件。

- 收益：实现极简，几分钟可完成
- 代价：后续命令读取 `metadata.json` / `MEMORY.md` 时会失败；
  用户需要手动创建这些文件，体验差

#### 方案 B：结构化初始化 + 自检

创建目录 + 写入模板文件内容 + 已有时执行自检报告。

- 收益：开箱即用，多次执行安全，后续命令不会因缺失文件报错
- 代价：需要设计 `metadata.json` schema、自检逻辑、初始文件模板；
  实现复杂度中等

#### 方案 C：不处理（基线）

不实现 `yzrws init`，让用户手动创建目录和文件。

- 适用于：项目极早期、仅自己使用、目录结构频繁变动时

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| 全新初始化 | 仅空目录 | 目录 + 模板内容 | 用户手动 |
| 部分存在 | 无法处理 | 检测缺失项，只补不覆盖 | 用户手动 |
| 幂等性 | 无反馈 | "已就绪" + 自检报告 | — |
| 后续命令兼容 | 需额外检查文件存在性 | 可直接读取 | 需额外检查 |
| 实现复杂度 | 低 | 中等 | — |

### 推荐方案

推荐方案 B。

理由：

1. workspace 是长期使用的运行时目录，用户必然会在升级后、误删文件后多次执行 init
2. 幂等性和自检能力是刚需——方案 A 无法处理部分存在和幂等重跑场景
3. 模板文件内容（特别是 `metadata.json` 和 `MEMORY.md`）是后续命令的基础，
   缺少它们会导致所有命令失败
4. 中等复杂度可控，不会过度设计

### 否决理由

- **方案 A**：空目录没有可用性——后续命令依赖 `metadata.json` 和 `MEMORY.md`，
  用户必须手动创建，违背工具化初衷
- **不处理**：手动创建 5 个目录 + 3 个文件的流程容易出错，
  且无法保证不同用户的工作区结构一致

## 初始化流程

```text
yzrws init
  │
  ├── 1. 前置检查
  │     ├── 确定 workspace 路径（默认 ~/yzr_workspace）
  │     ├── 检查路径是否被文件占用 → 报错退出
  │     └── 检查路径写权限 → 报错退出
  │
  ├── 2. 判断状态
  │     ├── 目录不存在 → 进入"全新初始化"流程
  │     └── 目录已存在 → 进入"补全 + 自检"流程
  │
  ├── 3a. 全新初始化
  │     ├── mkdir -p 创建 workspace 目录
  │     ├── 创建子目录：knowledge/、.config/
  │     ├── 写入初始文件：metadata.json、MEMORY.md
  │     └── 输出创建报告
  │
  ├── 3b. 补全 + 自检
  │     ├── 逐项检查必需目录和文件
  │     ├── 缺失的目录 → 创建
  │     ├── 缺失的文件 → 写入模板内容
  │     ├── 已有的文件 → 跳过（不覆盖）
  │     └── 输出自检报告
  │
  └── 4. 输出结果
        ├── 成功：列出创建 / 补全 / 已存在的项目清单
        └── 失败：列出错误项和修复建议
```

## Workspace 目录结构与初始内容

### 目录结构

```text
~/yzr_workspace
├── knowledge/          # 全局共享知识库（按需懒加载）
├── MEMORY.md           # 跨工作项长期记忆
├── metadata.json       # 工作区元数据
└── .config/            # 工作区级配置
```

> 工作项目录（`<work-item>/`）由 `yzrws create workitem` 创建，
> 不在 `init` 的初始化范围内。

### metadata.json

初始化时写入最小初始值：

```jsonc
// ~/yzr_workspace/metadata.json（初始状态）
{
  "version": "1.0",
  "created_at": "<当前时间>",
  "updated_at": "<当前时间>"
}
```

完整 schema（含 `stats`、`recent_workitems` 等字段）由其他命令在运行过程中逐步填充。
详细的字段定义和维护策略见 [`metadata_design.md`](./metadata_design.md)。

### MEMORY.md

```markdown
# MEMORY.md — 跨工作项长期记忆

> 本文件记录跨工作项的长期决策与偏好。
> 工作项内部的记忆请写到对应工作项目录下的 CLAUDE.md 中。
```

- 仅写入骨架模板，不写入具体内容
- 用户的记忆数据由日常使用中逐步积累，`init` 不会覆盖已有内容

### knowledge/ 目录

- 创建空目录即可
- 由于 git 不允许跟踪空目录，如果 workspace 纳入版本控制，
  需要在 `knowledge/` 下放置 `.gitkeep`

### .config/ 目录

- 创建空目录即可
- 用于存放工作区级配置文件（如未来的 workspace 级 lint 规则）
- 同样需要 `.gitkeep` 以支持版本控制

## 自检逻辑

自检是 `init` 的核心能力——无论是全新初始化还是部分存在场景，
都需要在完成后输出结构化的自检报告。

### 检查项清单

```text
检查项                    类型     缺失时行为
─────────────────────────────────────────────────
workspace 目录             目录     创建
knowledge/ 目录            目录     创建
.config/ 目录              目录     创建
metadata.json              文件     写入模板内容
metadata.json.version      字段     报错（需人工确认版本）
MEMORY.md                  文件     写入骨架模板
```

### 自检输出格式

```sh
$ yzrws init

=== Workspace 初始化 ===

路径：~/yzr_workspace

  [已存在] workspace 目录
  [已存在] knowledge/
  [已存在] .config/
  [已存在] metadata.json (v1.0)
  [已存在] MEMORY.md

=== 自检通过，workspace 已就绪 ===
```

补全场景的输出：

```sh
$ yzrws init

=== Workspace 初始化 ===

路径：~/yzr_workspace

  [已存在] workspace 目录
  [已存在] knowledge/
  [创建]   .config/              ← 本次补全
  [已存在] metadata.json (v1.0)
  [创建]   MEMORY.md             ← 本次补全

=== 自检通过，workspace 已就绪 ===
```

### 错误输出格式

```sh
$ yzrws init

=== Workspace 初始化 ===

路径：~/yzr_workspace

  [错误] ~/yzr_workspace 是一个文件，不是目录
         请移除该文件或指定其他路径

=== 初始化失败 ===
```

### metadata.json 版本兼容

当 `metadata.json` 已存在但 `version` 字段与当前工具期望版本不一致时：

- **version 相同**：正常通过
- **version 更低**：输出警告 `metadata.json 版本为 X，当前期望 Y，建议运行 yzrws migrate`
  （`migrate` 命令暂不实现，仅提示）
- **version 更高**：输出错误 `metadata.json 版本 X 高于当前工具支持的 Y，请升级 yzrws`

## 命令接口

### 命令格式

```sh
yzrws init
```

当前不支持任何参数。后续可扩展：

- `--path <dir>`：指定 workspace 路径（当前硬编码为 `~/yzr_workspace`）
- `--force`：强制覆盖已有的初始文件（当前不实现）
- `--check`：仅自检，不做任何修改（当前不实现）

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 初始化成功（含全新创建和幂等重跑） |
| 1 | 初始化失败（路径被占用、无权限、version 不兼容等） |

### Workspace 路径确定

当前版本硬编码为 `~/yzr_workspace`，确定逻辑：

```python
import os
from pathlib import Path


def get_workspace_path() -> Path:
    """确定 workspace 路径。当前固定为 ~/yzr_workspace。"""
    return Path(os.environ.get("YZR_WORKSPACE", "") or "~/yzr_workspace").expanduser()
```

> 预留了 `YZR_WORKSPACE` 环境变量作为临时覆盖手段，方便测试和特殊场景。
> 正式的 `--path` 参数在后续迭代中实现。

## 文件归属

| 文件 | 说明 | 纳入版本控制 |
| --- | --- | --- |
| `scripts/python/workspace.py` | workspace 初始化 / 自检逻辑 | ✓ |
| `bin/yzrws` | 主命令入口（调用 workspace.py） | ✓ |
| `~/yzr_workspace/metadata.json` | 运行时工作区元数据 | 由用户决定 |
| `~/yzr_workspace/MEMORY.md` | 运行时跨工作项记忆 | 由用户决定 |
| `~/yzr_workspace/knowledge/` | 运行时全局知识库 | 由用户决定 |
| `~/yzr_workspace/.config/` | 运行时工作区配置 | 由用户决定 |

> `~/yzr_workspace/` 下的文件是运行时产物，不在本仓库的版本控制范围内。
> 是否纳入用户自己的版本控制由用户自行决定。

## 与其他文档的关系

- [`command_design.md`](./command_design.md)：定义了 `yzrws init` 的命令骨架，
  本文档是其细化
- [`metadata_design.md`](./metadata_design.md)：`metadata.json` 的完整 schema 设计
  （当前为骨架文档，后续补充）
- [`session_design.md`](./session_design.md)：session 相关元数据在 workitem 级别管理，
  与 workspace 级别的 `metadata.json` 是不同层次
