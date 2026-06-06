# Workitem 创建设计

## 概述

`yzrws create workitem <name>` 用于在工作区中创建一个新的工作项。
每个工作项是一个独立目录，包含完整的目录结构和初始文件，
绑定一个可恢复的 Code Agent Session，支持断点续传和知识沉淀。

创建流程需要完成三件事：校验输入合法性、创建目录与模板文件、更新 workspace 级元数据。

## 场景分析

### 场景一：正常创建

**触发条件**：用户提供一个合法的工作项名称，workspace 已初始化。

**期望行为**：在 `~/yzr_workspace/` 下创建同名子目录，生成全部初始文件，
更新 `metadata.json` 的统计信息，输出创建报告。

**困难与挑战**：

- 需要生成 6 个文件 / 目录的初始内容，每个模板都要合理且可被后续命令直接消费
- `CLAUDE.md` 的初始内容需要有结构化引导，帮助用户快速补充上下文
- `setting.json` 的默认值策略需要与全局配置和引擎选择逻辑衔接

### 场景二：名称已存在

**触发条件**：用户指定的名称在 workspace 下已有对应目录。

**期望行为**：输出"workitem xxx 已存在"，退出码 0，不做任何修改。

**困难与挑战**：

- 需要区分"同名目录"和"同名文件"——目录存在是幂等回显，文件存在是错误
- 不能覆盖已有工作项的任何内容

### 场景三：workspace 未初始化

**触发条件**：`~/yzr_workspace/` 不存在，或缺少 `metadata.json`。

**期望行为**：提示用户先执行 `yzrws init`，退出码 1。

**困难与挑战**：

- 需要明确"未初始化"的判定条件——不能只检查目录是否存在，还要检查关键文件
- 错误信息需要可操作：告诉用户执行什么命令来修复

### 场景四：名称不合法

**触发条件**：用户提供的名称包含非法字符（空格、路径分隔符、保留名称等）。

**期望行为**：给出清晰的错误提示和命名规则说明，退出码 1。

**困难与挑战**：

- 命名规则需要在"严格"和"方便"之间取平衡——太严格影响体验，太宽松可能导致路径问题
- 需要防止路径穿越攻击（如 `../etc`）

### 场景五：创建后直接启动

**触发条件**：用户希望创建完工作项后立即进入 Agent 会话。

**期望行为**：通过 `--start` 参数串联创建和启动流程，创建完成后自动执行 `yzrws start`。

**困难与挑战**：

- 串联两个命令时，创建失败不应触发启动
- 需要传递 `--engine` 等参数到 `start` 命令

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 正常创建 | 名称合法、workspace 已初始化 | 模板内容定义 | §创建流程 / §模板内容 |
| 名称已存在 | 目录已存在 | 幂等处理 | §命令接口 |
| workspace 未初始化 | 目录 / metadata.json 不存在 | 可操作的错误提示 | §前置检查 |
| 名称不合法 | 特殊字符 / 路径穿越 | 命名规则设计 | §命名规则 |
| 创建后启动 | `--start` 参数 | 命令串联 | §命令接口 |

## 方案选择

### 备选方案

#### 方案 A：最小创建

只创建目录和 `workitem.json`，其他文件由用户手动创建或在首次 `start` 时按需生成。

- 收益：实现简单，创建速度快
- 代价：用户需要手动创建 `CLAUDE.md` / `setting.json` 等文件，
  且 `metadata.json` 不更新，后续 `yzrws list` 无法正确统计

#### 方案 B：完整创建 + 元数据同步

创建全部目录和文件，写入合理的模板内容，同步更新 `metadata.json`。

- 收益：开箱即用，创建后直接 `yzrws start` 即可进入工作；
  workspace 级统计保持准确
- 代价：需要设计每个文件的模板内容和命名校验规则；实现复杂度中等

#### 方案 C：不处理（基线）

不实现 `create workitem`，让用户手动 `mkdir` + 创建文件。

- 适用于：项目极早期、不需要标准化工具流程时

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| 创建后是否可直接使用 | 需手动补文件 | 可直接 start | 全部手动 |
| metadata.json 同步 | 不同步 | 自动同步 | 不同步 |
| 模板内容 | 无 | 结构化引导 | 无 |
| 命名校验 | 无 | 有 | 无 |
| 实现复杂度 | 低 | 中等 | — |

### 推荐方案

推荐方案 B。

理由：

1. 创建后的即时可用性是核心体验——方案 A 需要用户手动补文件，违背工具化初衷
2. `metadata.json` 同步是 `yzrws list` / `yzrws status` 正确工作的基础
3. `CLAUDE.md` 的模板引导可以显著降低用户补充上下文的门槛

### 否决理由

- **方案 A**：缺少 `setting.json` 会导致 `yzrws start` 无法确定引擎；
  不同步 `metadata.json` 会导致统计数据不一致
- **不处理**：手动创建 2 个目录 + 4 个文件的流程容易出错，
  且无法保证不同工作项的结构一致

## 创建流程

```text
yzrws create workitem <name> [--engine <engine>] [--start]
  │
  ├── 1. 前置检查
  │     ├── 校验 workspace 是否已初始化
  │     │     └── 检查 ~/yzr_workspace/metadata.json 是否存在 → 缺失则提示 yzrws init
  │     ├── 校验名称合法性（见 §命名规则）
  │     │     └── 不合法则报错退出
  │     └── 检查目标路径
  │           ├── 目录已存在 → 回显"已存在"，退出码 0
  │           ├── 同名文件已存在 → 报错退出
  │           └── 不存在 → 继续创建
  │
  ├── 2. 创建目录结构
  │     ├── mkdir <workspace>/<name>/
  │     ├── mkdir <workspace>/<name>/raw/
  │     └── mkdir <workspace>/<name>/local_wiki/
  │
  ├── 3. 写入初始文件
  │     ├── workitem.json      # 元数据
  │     ├── setting.json       # 引擎配置
  │     └── CLAUDE.md          # 工作项上下文（带模板引导）
  │
  ├── 4. 更新 workspace 元数据
  │     ├── metadata.json: stats.workitem_count++
  │     ├── metadata.json: stats.active_workitem_count++
  │     ├── metadata.json: recent_workitems 追加新条目
  │     └── metadata.json: updated_at 刷新
  │
  ├── 5. 输出创建报告
  │     └── 列出创建的目录和文件清单
  │
  └── 6. 可选：串联启动（--start）
        └── 创建成功后自动执行 yzrws start <name>
```

## 模板内容

### workitem.json

```jsonc
// <workitem>/workitem.json
{
  "name": "<workitem_name>",                     // 工作项名称（与目录名一致）
  "created_at": "<当前时间>",                     // 创建时间
  "status": "active"                             // 初始状态为 active
}
```

- `name` 与目录名保持一致，作为冗余字段方便迁移和识别
- `status` 初始值为 `"active"`，后续由 `archive` / `complete` 等命令变更

### setting.json

```jsonc
// <workitem>/setting.json
{
  "engine": "<引擎名称>",                         // 由 --engine 参数或全局配置决定
  "model": null,                                 // 运行时按引擎选择策略回退
  "provider": null,                              // 运行时按引擎选择策略回退
  "env": {}                                      // 传递给引擎的额外环境变量
}
```

`engine` 字段的确定逻辑（优先级从高到低）：

1. `--engine <engine>` 命令行参数
2. 兜底值 `"claude-code"`（来自 `commands/_create_workitem.py::DEFAULT_ENGINE`）

`model` 和 `provider` 初始为 `null`，运行时由引擎适配器按以下策略查找
（详见 [`provider_design.md §回退链`](./provider_design.md)）：

1. `setting.json.provider` 非 `null` → 取该 Provider
2. `<workspace>/.config/provider.json` 的 `default` 字段指向的 Provider
3. 引擎自身的内置默认

> Provider 配置统一存放在 workspace 下的 `<workspace>/.config/provider.json`，
> 不维护用户级副本。显式设置了 `provider` 的工作项不受上层配置变更影响。

### CLAUDE.md

```markdown
# <workitem_name>

> 本文件是该工作项的上下文说明，Code Agent 启动时自动加载。

## 目标

<!-- 该工作项要达成什么目标？ -->

## 关键决策

<!-- 已做出的重要设计决策及其理由 -->

## 约束条件

<!-- 技术约束、时间约束、依赖限制等 -->

## 相关资源

<!-- 关联的设计文档、参考资料、外部链接 -->
```

- 结构化引导帮助用户快速补充工作项上下文
- `<!-- -->` 注释在 Markdown 渲染时不可见，不影响阅读
- 用户可以根据需要删除或追加章节

### 空目录的 .gitkeep

`raw/` 和 `local_wiki/` 创建为空目录。如果 workspace 纳入版本控制：

- `local_wiki/` 下放 `.gitkeep`（知识文件可能需要版本追踪）
- `raw/` 不放 `.gitkeep`（原始语料通常不纳入版本控制，符合 README 约定）

## 命名规则

### 合法名称

- 只允许小写字母、数字、连字符（`-`）和下划线（`_`）
- 长度限制：1-64 个字符
- 不能以连字符或下划线开头
- 不能是保留名称

### 正则表达式

```text
^[a-z0-9][a-z0-9_-]{0,63}$
```

### 保留名称

以下名称不可用作工作项名称：

| 保留名 | 原因 |
| --- | --- |
| `knowledge` | 与全局知识库目录冲突 |
| `config` | 与 `.config/` 目录冲突（避免大小写混淆） |
| `raw` | 语义冲突，raw 是工作项内部概念 |

### 错误提示示例

```sh
$ yzrws create workitem "My Task"

[错误] 工作项名称不合法："My Task"

命名规则：
  • 只允许小写字母、数字、连字符（-）和下划线（_）
  • 长度 1-64 个字符
  • 不能以连字符或下划线开头
  • 不能是保留名称（knowledge, config, raw）

示例：my-task, api_refactor, v2-migration
```

## 前置检查

`create workitem` 在执行前需要确认 workspace 处于可用状态：

```text
检查项                         缺失时行为
────────────────────────────────────────────
~/yzr_workspace/ 目录          报错：提示执行 yzrws init
~/yzr_workspace/metadata.json  报错：提示执行 yzrws init
目标路径无同名文件              报错：路径被文件占用
目标路径无同名目录              回显"已存在"，退出码 0
```

### workspace 未初始化的错误提示

```sh
$ yzrws create workitem my-task

[错误] 工作区未初始化：~/yzr_workspace/metadata.json 不存在

请先执行以下命令初始化工作区：
  yzrws init
```

## 元数据同步

创建成功后，需要对 `~/yzr_workspace/metadata.json` 做以下增量更新：

| 字段 | 更新逻辑 |
| --- | --- |
| `stats.workitem_count` | +1 |
| `stats.active_workitem_count` | +1 |
| `recent_workitems` | 追加 `{name, status: "active", last_active_at: <当前时间>}`，保持 top 5 |
| `updated_at` | 刷新为当前时间 |

> 详细的 `metadata.json` schema 和维护策略见
> [`metadata_design.md`](./metadata_design.md)。

## 命令接口

### 命令格式

```sh
yzrws create workitem <name> [--engine <engine>] [--start]
```

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `<name>` | ✓ | 工作项名称，需符合命名规则 |
| `--engine <engine>` | ✗ | 指定 Agent 引擎（覆盖全局默认值） |
| `--start` | ✗ | 创建完成后自动执行 `yzrws start <name>` |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 创建成功，或工作项已存在（幂等） |
| 1 | 创建失败（名称不合法、workspace 未初始化、路径被占用等） |

### 输出示例

正常创建：

```sh
$ yzrws create workitem api-refactor

=== 创建工作项 ===

名称：api-refactor
路径：~/yzr_workspace/api-refactor
引擎：claude-code

  [创建] api-refactor/
  [创建] api-refactor/raw/
  [创建] api-refactor/local_wiki/
  [创建] api-refactor/workitem.json
  [创建] api-refactor/setting.json
  [创建] api-refactor/CLAUDE.md
  [更新] metadata.json (workitem_count: 4 → 5)

=== 创建成功 ===

提示：执行 yzrws start api-refactor 开始工作
```

名称已存在：

```sh
$ yzrws create workitem api-refactor

=== 创建工作项 ===

工作项 api-refactor 已存在：~/yzr_workspace/api-refactor
```

## 文件归属

| 文件 | 说明 | 纳入版本控制 |
| --- | --- | --- |
| `src/yzrws/commands/create.py` | workitem 创建入口（yzrws create workitem） | ✓ |
| `~/yzr_workspace/<name>/workitem.json` | 运行时工作项元数据 | 由用户决定 |
| `~/yzr_workspace/<name>/setting.json` | 运行时引擎配置 | 由用户决定 |
| `~/yzr_workspace/<name>/CLAUDE.md` | 运行时工作项上下文 | 由用户决定 |
| `~/yzr_workspace/<name>/raw/` | 运行时原始语料目录 | 否（README 约定） |
| `~/yzr_workspace/<name>/local_wiki/` | 运行时本地知识目录 | 由用户决定 |

> `~/yzr_workspace/` 下的文件是运行时产物，不在本仓库的版本控制范围内。

## 与其他文档的关系

- [`command_design.md`](./command_design.md)：定义了 `yzrws create workitem` 的命令骨架，
  本文档是其细化
- [`workspace_init_design.md`](./workspace_init_design.md)：`create workitem` 依赖 workspace 已初始化
- [`metadata_design.md`](./metadata_design.md)：创建后的 `metadata.json` 增量更新逻辑
- [`multi_agent_design.md`](./multi_agent_design.md)：`setting.json` 的完整 schema 和引擎选择策略
- [`session_design.md`](./session_design.md)：工作项创建时不生成 `session.json`，
  首次 `yzrws start` 时才创建
- [`provider_design.md`](./provider_design.md)：`provider: null` 时的回退链和 workspace 级 Provider 配置
