# 命令集设计

## 初始化 workspace

### 命令格式

```text
yzrws init
```

- **执行入口**：`bin/yzrws`（带 shebang 的 Python 脚本）；等价方式 `python -m yzrws init`
- **参数**：当前版本不接收任何参数（`--path` / `--force` / `--check` 规划中，详见
  [`workspace_init_design.md`](./workspace_init_design.md) §命令接口）
- **工作区路径解析**：
  - 优先读 `YZR_WORKSPACE` 环境变量（空串视为未设置）
  - 否则用默认值 `~/yzr_workspace`
  - 自动展开 `~`

### 行为

`yzrws init` 是 `yzrws` 工具的第一步命令，负责在本地创建并初始化 workspace
目录结构。处理 4 类场景：

1. **全新初始化**：目录不存在时按 `README.md` 规定的目录树完整创建，
   并写入 6 项检查清单中的所有目录与文件
2. **部分存在**：目录已存在但缺少部分子项时，仅补全缺失项，**不覆盖已有内容**（幂等）
3. **幂等重跑**：所有项已就绪时不修改任何文件，输出"自检通过"
4. **致命错误**：目标路径被文件占用 / 无写权限时，**不做任何修改**并返回退出码 1

6 项检查清单：

| 检查项 | 类型 | 缺失时行为 |
| --- | --- | --- |
| workspace 目录 | 目录 | `mkdir -p` 创建 |
| `knowledge/` | 目录 | 创建 + 写入 `.gitkeep`（支持空目录纳入版本控制） |
| `.config/` | 目录 | 创建 + 写入 `.gitkeep` |
| `metadata.json` | 文件 | 原子写入最小集 `{version, created_at, updated_at}` |
| `metadata.json.version` 字段 | 字段 | 文件缺失时由上一项统一处理；存在但 version 不兼容则报错 |
| `MEMORY.md` | 文件 | 原子写入 4 行中文骨架 |

详细的 6 项设计意图与 `metadata.json` schema 见
[`workspace_init_design.md`](./workspace_init_design.md) 与 [`metadata_design.md`](./metadata_design.md)。

### 输出格式

成功（含全新 / 补全 / 幂等）：

```text
=== Workspace 初始化 ===

路径：/Users/<user>/yzr_workspace

  [已存在] workspace 目录
  [创建]   knowledge/
  [创建]   .config/
  [创建]   metadata.json
  [已存在] metadata.json.version 字段  v1.0
  [创建]   MEMORY.md

=== 自检通过，workspace 已就绪 ===
```

补全场景（部分子项已存在）：

```text
  [已存在] workspace 目录
  [已存在] knowledge/
  [创建]   .config/              ← 本次补全
  [已存在] metadata.json
  [已存在] metadata.json.version 字段  v1.0
  [创建]   MEMORY.md             ← 本次补全
```

致命错误：

```text
=== Workspace 初始化 ===

路径：/Users/<user>/yzr_workspace

  [错误] /Users/<user>/yzr_workspace 是一个文件，不是目录
         请移除该文件或指定其他路径

=== 初始化失败 ===
```

状态标签：

| 标签 | 含义 | 是否阻塞成功 |
| --- | --- | --- |
| `[已存在]` | 本次检查时已就绪，未做修改 | 否 |
| `[创建]` | 本次 init 写入 | 否 |
| `[警告]` | 可继续但需关注（如 `metadata.json` version 较低、JSON 损坏） | 否 |
| `[错误]` | 致命（路径被占用 / 无写权限 / `metadata.json` version 更高） | 是 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（含全新初始化、幂等重跑、含 `[警告]` 项的初始化） |
| 1 | 失败（致命前置检查失败 / `metadata.json` version 不兼容） |

### 使用示例

```sh
# 默认路径 ~/yzr_workspace 初始化
$ yzrws init

# 自定义工作区路径（仅本次生效；正式参数 --path 待实现）
$ YZR_WORKSPACE=/tmp/test_ws yzrws init

# 验证初始化产物
$ ls -la ~/yzr_workspace
$ cat ~/yzr_workspace/metadata.json
$ cat ~/yzr_workspace/MEMORY.md
```

### 实现细节

- **原子写文件**：`metadata.json` / `MEMORY.md` 通过 `tempfile.mkstemp` + `os.replace`
  写入，写一半断电不会留下半截文件
- **时区感知时间戳**：`metadata.json` 的 `created_at` / `updated_at` 使用
  `datetime.now().astimezone().isoformat(timespec="seconds")`，带 `+08:00` 这类本地偏移
- **check 与 act 解耦**：init 内部先 `inspect_state` 一次得到现状，执行创建后再
  `inspect_state` 一次生成报告；"是否写入"只来自 `path.exists()`，不依赖中间状态
- **本次创建跟踪**：`init` 内部用 `created_paths` 集合记录本轮新建的路径，
  在最终报告里把它们标记为 `[创建]`（与既有的 `[已存在]` 形成视觉差异）
- **CJK 标签对齐**：报告里的状态标签按 `unicodedata.east_asian_width` 计算显示宽度，
  把 `name` 列起点对齐到本批最宽标签

### 相关文档

- [`workspace_init_design.md`](./workspace_init_design.md)：workspace 初始化的完整设计
  （场景分析、方案选择、初始化流程、6 项自检、命令接口、版本兼容）
- [`metadata_design.md`](./metadata_design.md)：`metadata.json` 完整 schema、字段分类、
  维护策略、版本兼容

## 创建 workitem

### 命令格式

```text
yzrws create workitem <name> [--engine <engine>] [--start]
```

- **执行入口**：`bin/yzrws create workitem <name>`（通过 `python -m yzrws create workitem <name>` 等价调用）
- **参数**：

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `<name>` | ✓ | 工作项名称，需符合命名规则（见下方 §命名规则） |
| `--engine <engine>` | ✗ | 指定 Agent 引擎，覆盖全局默认值 |
| `--start` | ✗ | 创建完成后自动执行 `yzrws start <name>` |

### 命名规则

- 只允许小写字母、数字、连字符（`-`）和下划线（`_`）
- 长度 1-64 个字符
- 不能以连字符或下划线开头
- 不能是保留名称：`knowledge`、`config`、`raw`
- 正则：`^[a-z0-9][a-z0-9_-]{0,63}$`

### 行为

`yzrws create workitem <name>` 在 workspace 下创建一个完整的工作项目录。处理 4 类场景：

1. **正常创建**：workspace 已初始化且名称合法时，创建目录结构（`<name>/`、`raw/`、`local_wiki/`）、
   写入初始文件（`workitem.json`、`setting.json`、`CLAUDE.md`），并同步更新 `metadata.json`
2. **名称已存在**：同名目录已存在时，回显"workitem xxx 已存在"，退出码 0（幂等）
3. **workspace 未初始化**：`~/yzr_workspace/metadata.json` 不存在时，提示执行 `yzrws init`，退出码 1
4. **名称不合法 / 路径被占用**：名称违反命名规则或同名文件（非目录）已存在时，报错退出码 1

创建完成后 `metadata.json` 增量更新：
`stats.workitem_count++`、`stats.active_workitem_count++`、`recent_workitems` 追加（top 5）、
`updated_at` 刷新。

完整的创建流程、模板内容、引擎回退链和元数据同步逻辑见
[`workitem_create_design.md`](./workitem_create_design.md)。

### 输出格式

正常创建：

```text
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
  [更新] metadata.json (workitem_count: 0 → 1)

=== 创建成功 ===

提示：执行 yzrws start api-refactor 开始工作
```

名称已存在：

```text
=== 创建工作项 ===

工作项 api-refactor 已存在：~/yzr_workspace/api-refactor
```

名称不合法：

```text
[错误] 工作项名称不合法："My Task"

命名规则：
  • 只允许小写字母、数字、连字符（-）和下划线（_）
  • 长度 1-64 个字符
  • 不能以连字符或下划线开头
  • 不能是保留名称（knowledge, config, raw）

示例：my-task, api_refactor, v2-migration
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 创建成功，或工作项已存在（幂等） |
| 1 | 创建失败（名称不合法、workspace 未初始化、路径被文件占用等） |

### 实现细节

- **原子写文件**：`workitem.json` / `setting.json` / `CLAUDE.md` 通过 `tempfile` + `os.replace`
  写入，写失败时清理临时文件，不留半截内容
- **引擎回退链**：`--engine` 参数 → 兜底值 `"claude-code"`
  （来自 `commands/_create_workitem.py::DEFAULT_ENGINE`），详见
  [`workitem_create_design.md`](./workitem_create_design.md) §setting.json
- **时区感知时间戳**：`workitem.json` 的 `created_at` 使用
  `datetime.now().astimezone().isoformat(timespec="seconds")`，带 `+08:00` 这类本地偏移
- **metadata.json 兼容**：`stats` / `recent_workitems` 字段缺失时自动初始化，
  兼容 `init` 写入的最小集 `{version, created_at, updated_at}`
- **local_wiki/.gitkeep**：`local_wiki/` 下写入 `.gitkeep` 以支持版本控制；
  `raw/` 不放（原始语料通常不纳入版本控制，符合 README 约定）
- **--start 串联**：通过 `subprocess` 调用 `yzrws start`，创建失败时不触发启动；
  `yzrws` 不在 PATH 时优雅降级

### 相关文档

- [`workitem_create_design.md`](./workitem_create_design.md)：完整设计文档
  （场景分析、方案选择、模板内容、命名规则、元数据同步）
- [`metadata_design.md`](./metadata_design.md)：`metadata.json` 增量更新逻辑
- [`workspace_init_design.md`](./workspace_init_design.md)：`create workitem` 依赖 workspace 已初始化
- [`multi_agent_design.md`](./multi_agent_design.md)：`setting.json` 完整 schema 和引擎选择策略
- [`provider_design.md`](./provider_design.md)：`provider: null` 时的回退链
- [`session_design.md`](./session_design.md)：工作项创建时不生成 `session.json`，
  首次 `yzrws start` 时才创建

## 列举 workitem

### 命令格式

```text
yzrws list
```

- **执行入口**：`bin/yzrws list`（通过 `python -m yzrws list` 等价调用）
- **参数**：无

### 行为

`yzrws list` 列举 workspace 下所有工作项及其元数据。处理 3 类场景：

1. **正常工作项列表**：workspace 已初始化且包含工作项时，以表格形式展示
   NAME / STATUS / ENGINE / CREATED 四列，按 `created_at` 降序排序（最新的在前）
2. **空 workspace**：workspace 已初始化但无任何工作项时，输出"尚未创建任何工作项"，
   附带 `yzrws create workitem <name>` 命令提示
3. **workspace 未初始化**：`~/yzr_workspace/metadata.json` 不存在时，
   提示执行 `yzrws init`，退出码 1

### 输出格式

正常列表：

```text
=== 工作项列表 ===

NAME           STATUS  ENGINE       CREATED
-------------  ------  -----------  ----------
gamma-bugfix   active  claude-code  2026-06-06
beta-feature   active  opencode     2026-06-06
alpha-project  active  claude-code  2026-06-06
```

空 workspace：

```text
=== 工作项列表 ===

尚未创建任何工作项。

提示：执行 yzrws create workitem <name> 创建工作项
```

workspace 未初始化：

```text
[错误] 工作区未初始化：~/yzr_workspace/metadata.json 不存在

请先执行以下命令初始化工作区：
  yzrws init
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（含正常列表和空 workspace） |
| 1 | 失败（workspace 未初始化） |

### 实现细节

- **工作项识别**：扫描 workspace 下所有包含 `workitem.json` 的子目录
- **元数据来源**：
  - `workitem.json` → name / status / created_at
  - `setting.json` → engine（可选，缺失时 ENGINE 列显示 `—`）
- **日期格式化**：将 ISO 8601 时间戳（如 `2026-06-06T12:00:00+08:00`）格式化为 `YYYY-MM-DD`
- **列宽动态计算**：根据实际数据值长度动态调整列宽，保证表头和数据对齐
- **边缘情况处理**：
  - `workitem.json` 解析失败 → 静默跳过该工作项
  - `workitem.json` 缺失字段 → 显示 `—` 占位符
  - 缺少 `setting.json` → ENGINE 列显示 `—`
- **排序**：按 `created_at` 原始字符串降序排序（ISO 8601 格式天然支持字典序排序）

### 相关文档

- [`metadata_design.md`](./metadata_design.md)：`metadata.json` 的 `stats.workitem_count` 字段
- [`workspace_init_design.md`](./workspace_init_design.md)：`list` 命令依赖 workspace 已初始化
- [`workitem_create_design.md`](./workitem_create_design.md)：`workitem.json` 和 `setting.json` 的完整 schema

## 打开 workitem

### 命令格式

```text
yzrws start <name> [--engine <engine>]
```

- **执行入口**：`bin/yzrws start <name>`（通过 `python -m yzrws start <name>` 等价调用）
- **参数**：

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `<name>` | ✓ | 工作项名称 |
| `--engine <engine>` | ✗ | 指定引擎（自动创建或切换引擎时使用；缺省从 setting.json 读） |

### 行为

`yzrws start <name>` 打开工作项并启动 Agent 会话。处理 4 类场景：

1. **自动创建**：工作项不存在时，自动调用 `create workitem` 逻辑创建，然后启动会话
2. **启动新会话**：工作项已存在且无 session 记录时，启动新会话
3. **恢复会话**：工作项已存在且有 session 记录时，自动恢复上次会话（无需 `--new` 标志）
4. **引擎切换**：`--engine` 参数与 `setting.json` 不同时，归档旧 session 并切换引擎

> session 恢复决策完全自动化：存在则恢复（无论 `setting.json` 是否被改过），不存在则新建。原 `--new` 标志已移除——`yzrws start` 只保留 `<name>` 必填 + `--engine` 可选两个参数。

### 输出格式

自动创建并启动：

```text
工作项 my-task 不存在，正在创建...

=== 创建工作项 ===

名称：my-task
路径：~/yzr_workspace/my-task
引擎：claude-code

  [创建] my-task/
  [创建] my-task/raw/
  [创建] my-task/local_wiki/
  [创建] my-task/workitem.json
  [创建] my-task/setting.json
  [创建] my-task/CLAUDE.md
  [更新] metadata.json (workitem_count: 0 → 1)

=== 创建成功 ===

提示：执行 yzrws start my-task 开始工作

创建工作项完成，继续启动会话...

=== 启动会话 ===

工作项：my-task
路径：~/yzr_workspace/my-task
引擎：claude-code

启动新会话

（Claude Code 交互式 TUI 启动...）

会话已正常退出
Session ID：abc123
```

恢复会话：

```text
=== 启动会话 ===

工作项：my-task
路径：~/yzr_workspace/my-task
引擎：claude-code

恢复会话：abc123

（Claude Code 恢复会话...）

会话已正常退出
Session ID：abc123
```

引擎切换：

```text
检测到引擎切换：claude-code → opencode
已归档旧 session 到：test-task/sessions/claude-code_20260606T154440.json

=== 启动会话 ===

工作项：test-task
路径：~/yzr_workspace/test-task
引擎：opencode

启动新会话

（OpenCode 交互式 TUI 启动...）
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（会话正常退出） |
| 1 | 失败（名称不合法、workspace 未初始化、引擎不可用等） |
| 非 0 | 引擎进程异常退出时透传其退出码 |

### 实现细节

- **自动创建**：复用 `create workitem` 的目录和文件创建逻辑，无需用户先执行 `create`
- **引擎选择**：优先级为 `--engine` 参数 → `setting.json` → 全局默认 → `claude-code`
- **引擎切换归档**：当 `session.json.engine` 与目标引擎不同时，自动归档旧 session 到
  `sessions/<engine>_<timestamp>.json`
- **历史 session 恢复**：切换回历史引擎时，自动查找 `sessions/` 目录下该引擎的最新 session
- **Session ID 提取**：会话结束后从引擎本地存储提取 session_id 并写入 `session.json`
- **规则同步**：OpenCode 启动前自动生成 `opencode.json` 桥接 `CLAUDE.md`；Claude Code 无需额外同步

### 相关文档

- [`multi_agent_design.md`](./multi_agent_design.md)：引擎抽象和适配器设计
- [`session_design.md`](./session_design.md)：session.json 结构和会话状态机
- [`workitem_create_design.md`](./workitem_create_design.md)：自动创建时复用的创建逻辑

## 管理 model provider

管理模型服务商的连接信息（Provider）。Provider 配置统一存放在
`<workspace>/.config/provider.json`，**不**维护用户级副本——所有 Provider
与 workspace 同生命周期。

### 命令格式

```text
yzrws model provider add    [--name <name>] [--base-url <url>] [--auth-key <key>] [--model <model>] [--agent-type <engine>]... [--set-default] [-y]
yzrws model provider list
yzrws model provider remove <name> [-y]
yzrws model provider set-default <name>
```

- **执行入口**：`bin/yzrws model provider <subcmd>`（通过 `python -m yzrws model provider <subcmd>` 等价调用）
- **参数**：

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `add --name` / `--base-url` / `--auth-key` / `--model` | ✗ | 非交互式参数；缺省时进入交互式输入（Auth Key 用 `getpass` 隐藏） |
| `add --agent-type` | ✗ | 该 provider 兼容的 engine（可多次指定，如 `--agent-type claude-code --agent-type opencode`）；缺省时表示兼容所有已注册 engine |
| `add --set-default` | ✗ | 强制将新 Provider 设为 workspace 默认 |
| `add -y` / `--yes` | ✗ | 同名 Provider 存在时跳过确认直接覆盖 |
| `remove <name>` | ✓ | 待删除的 Provider 名称 |
| `remove -y` / `--yes` | ✗ | 跳过确认直接删除 |
| `set-default <name>` | ✓ | 待设为默认的 Provider 名称 |

### 行为

`yzrws model provider` 在 workspace 下的 `<workspace>/.config/provider.json`
中增删改查 Provider。处理 4 类场景：

1. **添加 Provider**：workspace 已初始化时收集 4 个字段（Provider 名称 / Base URL /
   Auth Key / Model name），写盘；首个 Provider 自动标记为 `default`；同名 Provider
   需确认覆盖
2. **列出 Provider**：workspace 已初始化且 `provider.json` 存在时，读取并以
   NAME / BASE_URL / MODEL 三列展示，标注 `★ 默认`；空配置时输出"尚未配置任何 Provider"
3. **删除 Provider**：从 `provider.json` 移除指定 Provider；若是默认 Provider，
   同步清空 `default` 字段；删除前确认（`-y` 跳过）
4. **切换默认 Provider**：将 `default` 字段指向已存在的 Provider

### 输出格式

`add` 成功：

```text
=== 添加 Provider ===

目标文件：/Users/<user>/yzr_workspace/.config/provider.json

  [新增] Provider 'anthropic'
  [默认] 首个 Provider，已自动设为默认

=== 添加成功 ===
```

`add` 覆盖确认（拒绝）：

```text
=== 添加 Provider ===

目标文件：/Users/<user>/yzr_workspace/.config/provider.json

  [警告] Provider 'anthropic' 已存在于 /Users/<user>/yzr_workspace/.config/provider.json
确认覆盖？[y/N]: 
添加 Provider 已取消。
```

`list` 正常：

```text
=== Provider 列表 ===

NAME       BASE_URL                     MODEL               AGENT_TYPES
----------  ---------------------------  ------------------  ----------------
anthropic   https://api.anthropic.com    claude-sonnet-4-6   all              ★ 默认
my-gateway  https://gw.company.com/v1    gpt-4o              opencode
```

`list` 空配置：

```text
=== Provider 列表 ===

尚未配置任何 Provider。

提示：执行 yzrws model provider add 添加一个 Provider
```

`remove` 默认 Provider：

```text
=== 删除 Provider ===

目标文件：/Users/<user>/yzr_workspace/.config/provider.json
Provider：anthropic
  [警告] 警告：anthropic 是当前默认 Provider，删除后该层无默认
确认删除？[y/N]:   [删除] Provider 'anthropic'
  [警告] 该 Provider 是当前默认 Provider，default 已清空

=== 删除成功 ===
```

`remove` 引用警告（workspace 内仍有工作项的 `setting.json` 引用该 Provider）：

```text
  [警告] 以下工作项仍引用 Provider 'anthropic'：
    - api-refactor
    - doc-restructure

  这些工作项下次 yzrws start 时将沿用其 setting.json 中的 `model` /
  `provider`，按 [`provider_design.md §回退链`](./provider_design.md) 解析；如需解除引用，
  当前可用 `yzrws workitem unset-model <name>` 显式重设（`yzrws config set` 未实现）。
```

`set-default` 成功：

```text
已将默认 Provider 切换为：my-gateway
```

workspace 未初始化：

```text
[错误] 工作区未初始化：~/yzr_workspace/metadata.json 不存在

请先执行以下命令初始化工作区：
  yzrws init
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（含正常 add / list / remove / set-default） |
| 1 | 失败（名称不合法、Provider 不存在、workspace 未初始化、用户拒绝确认、`provider.json` JSON 损坏等） |

### 实现细节

- **配置位置**：所有 Provider 存放在 `<workspace>/.config/provider.json`，
  与 workspace 同生命周期；workspace 纳入版本控制时建议将 `.config/provider.json`
  加入 `.gitignore`（含 Auth Key）
- **原子写文件**：`provider.json` 通过 `tempfile.mkstemp` + `os.replace` 写入，
  写失败时清理临时文件，不留半截内容
- **Provider 命名规则**：正则 `^[a-z0-9][a-z0-9_-]{0,31}$`（1-32 字符，小写字母 / 数字开头）
- **Base URL 校验**：使用 `urllib.parse.urlparse` 校验至少包含 `scheme` 与 `netloc`
- **agent_types 校验**：每次 `--agent-type` 的取值必须存在于 `engine.list_engines()`；
  缺省 / 字段缺失时回退到所有已注册 engine（避免引入新 engine 时改动旧 provider.json）
- **agent_types 序列化**：仅在非空时写出到 `provider.json`；空列表不写出
- **首个默认**：添加第一个 Provider 时自动设为 `default`；`--set-default` 可强制覆盖
- **删除默认**：删除 `default` 指向的 Provider 后，同步清空 `default` 字段，
  不自动回退到首个 Provider（避免隐式行为）
- **覆盖保护**：同名 Provider 需交互式确认（`y` / `N`），`-y` 跳过
- **Auth Key 隐藏**：交互式输入时使用 `getpass.getpass`；CLI 传值时不隐藏（用户自行负责）
- **引用扫描**：删除 Provider 后扫描 workspace 下所有 `setting.json`，列出 `provider`
  字段引用该 Provider 的工作项，仅作警告不阻止删除
- **空配置序列化**：`providers` 为空时序列化为 `{}`（不写 `providers: {}` / `default: null`），
  便于下次 load 还原为空 `ProviderConfig`
- **错误信息**：JSON 损坏 / 字段缺失 / 类型错误统一抛 `ProviderConfigError`，
  由 `print_failure` 报告
- **与 workitem 兼容性**：被 `yzrws workitem set-model` 与 `yzrws start` 消费；
  set-model 在不兼容时报错，start 仅打印 WARN（允许临时 `--engine` 切换）

### 相关文档

- [`provider_design.md`](./provider_design.md)：Provider 配置的完整设计
  （场景分析、方案选择、Schema、回退链、创建流程、管理命令）
- [`multi_agent_design.md`](./multi_agent_design.md)：`setting.json` 的
  `provider` 字段引用本文档的 Provider 名称；`yzrws start` 启动时按回退链查找
- [`workitem_create_design.md`](./workitem_create_design.md)：创建工作项时
  `provider` 为 `null`，运行时按 `provider_design.md §回退链` 解析

## 配置 workitem

管理 workitem 级别的配置（主要是 Provider / model 绑定）。命令集：

- `set-model <name> --provider <name>`：把 workitem 绑定到 workspace 中已配置的某个 Provider
- `unset-model <name>`：解除绑定，恢复继承 workspace 默认
- `show <name>`：展示 workitem 完整配置与按回退链解析后的生效模型

### 命令格式

```text
yzrws workitem set-model <name> --provider <name>
yzrws workitem unset-model <name>
yzrws workitem show <name>
```

- **执行入口**：`bin/yzrws workitem <subcmd>`（通过 `python -m yzrws workitem <subcmd>` 等价调用）
- **参数**：

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `set-model <name>` | ✓ | 工作项名称 |
| `set-model --provider <name>` | ✓ | 目标 Provider 名称（必须是 workspace provider.json 中已配置的） |
| `unset-model <name>` | ✓ | 工作项名称 |
| `show <name>` | ✓ | 工作项名称 |

### 行为

`yzrws workitem` 读写 workitem 目录下的 `setting.json`（`provider` 字段）。
处理 4 类场景：

1. **设置模型绑定**：校验 workspace 已初始化、workitem 存在、目标 Provider
   在 workspace provider.json 中存在 → 把 `setting.json.provider` 设为 Provider 名称
2. **解除模型绑定**：校验前置条件 → 把 `setting.json.provider` 重置为 `null`
   （恢复继承 workspace `provider.json` 的 `default` 字段；进一步无 default 时
   引擎使用内置默认）
3. **展示 workitem**：读取 `setting.json` / `workitem.json` / workspace `provider.json`，
   按 `provider_design.md §回退链` 解析生效配置，以键值对三段式输出
4. **provider 不存在 / workitem 不存在**：报错退出码 1

### 输出格式

`set-model` 成功：

```text
=== 设置 Workitem 模型 ===

工作项：my-task
绑定 Provider：anthropic

  [设置] setting.json.provider = 'anthropic'

生效配置（启动时由 yzrws start 加载）：
  - model       ：claude-sonnet-4-6
  - base_url    ：https://api.anthropic.com
  - agent_types ：claude-code, opencode

=== 设置成功 ===
```

`set-model` 不兼容（workitem engine 不在 provider.agent_types 内）：

```text
[错误] Provider 'my-gateway' 不兼容当前 workitem 的 engine

  workitem：my-task
  当前 engine：claude-code
  Provider 'my-gateway' 仅支持：opencode

可执行以下操作之一：
  1. 切换 workitem 的 engine 后重试：
     yzrws start my-task --engine <compatible-engine>
  2. 选择一个兼容的 provider：
     yzrws workitem set-model my-task --provider <other>
  3. 修改该 provider 的 agent_types（先 unset-model，再 model provider add 覆盖）
```

`unset-model` 成功：

```text
=== 清除 Workitem 模型绑定 ===

工作项：my-task

  [清除] setting.json.provider = null

下次 yzrws start 将回退到 workspace provider.json 的 default；
若 workspace 也无 default，则使用引擎内置默认。

=== 清除成功 ===
```

`show` 正常：

```text
=== Workitem 详情 ===

基本信息：
  KEY         VALUE
  ---------   ----------------------------------------
  name        my-task
  path        /Users/<user>/yzr_workspace/my-task
  status      active
  created_at  2026-06-06T10:00:00+08:00

setting.json（原始）：
  KEY         VALUE
  ---------   ----------------------------------------
  engine      claude-code
  model       None
  provider    anthropic

生效配置（回退链结果）：
  KEY         VALUE
  ---------   ----------------------------------------
  source      workitem 显式设置
  provider    anthropic
  model       claude-sonnet-4-6
  base_url    https://api.anthropic.com
  agent_types claude-code, opencode
```

`show` 在 workitem 未设置 provider 时：

```text
生效配置（回退链结果）：
  KEY         VALUE
  ---------   ----------------------------------------
  source      workspace default
  provider    my-gateway
  model       gpt-4o
  base_url    https://gw.company.com/v1
  agent_types opencode
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 失败（workspace 未初始化、workitem 不存在、Provider 不存在、provider.agent_types 不兼容 workitem engine、JSON 损坏等） |

### 实现细节

- **修改字段**：`set-model` 只写 `setting.json.provider`；`model` 字段保持不变
  （与 `provider_design.md §回退链` 一致——workitem `model` 不允许单独覆盖）
- **原子写**：`setting.json` 通过 `workspace.atomic_write_json` 写入
- **前置检查**：复用 `commands/create.py` 的 `_check_workspace_initialized` 风格；
  workitem 存在性通过检查 `<name>/workitem.json` 文件判断
- **回退链解析**：`yzrws workitem show` 调用 `provider.resolve_model_config`，
  返回 `ResolvedModel`；`yzrws start` 同样调用该函数
- **set-model 不级联到 start**：仅修改 `setting.json`；`session.json` 的 model /
  provider 字段在下次 `yzrws start` 时才被刷新
- **engine 兼容性检查**：`set-model` 选中 provider 时若 `provider.agent_types`
  不包含 workitem 当前 `setting.json.engine` 则报错退出码 1
  （防止把"OpenAI 兼容网关"绑到 claude-code 引擎上）。`yzrws start` 在
  临时 `--engine` 切换到不兼容引擎时仅打印 WARN 不阻止——给用户"显式尝试"的余地

### 相关文档

- [`provider_design.md`](./provider_design.md)：§回退链 详细说明 Provider 查找顺序
  与 `default` 字段的作用
- [`command_design.md`](./command_design.md) §打开 workitem：`yzrws start` 启动时
  按回退链加载 model / base_url / auth_key 并注入到引擎
- [`multi_agent_design.md`](./multi_agent_design.md)：引擎适配器如何消费
  `ResolvedModel`（Claude Code 注入 `ANTHROPIC_*` 环境变量；OpenCode 写入
  `opencode.json` 的 `model` / `provider` 字段）
- [`provider_design.md`](./provider_design.md)：模型配置的回退链
