# Provider 配置设计

## 概述

Provider 是模型服务商的连接信息（Base URL、Auth Key、模型名称等）的封装。
`yzrws` 把所有 Provider 配置统一存放在 workspace 下的 `<workspace>/.config/provider.json`，
**不**维护用户级（`~/.config/yzrws/provider.json`）的副本——避免在多个 workspace
之间共享敏感凭据时引入歧义。

工作项（workitem）通过 `setting.json` 中的 `provider` 字段引用已配置的 Provider。
未指定时，按回退链自动查找 workspace 级 `default` 字段。

## 场景分析

### 场景一：配置默认模型

**触发条件**：用户首次使用 `yzrws`，或需要为 workspace 添加 / 切换默认模型。

**期望行为**：通过交互式命令输入 Base URL、Auth Key、Model name，
保存到 `<workspace>/.config/provider.json`，并标记为默认。

**困难与挑战**：

- Auth Key 是敏感信息，交互式输入时不应回显（需隐藏输入）
- 需要验证 Base URL 的格式合法性（至少是合法的 URL）
- 首次配置时自动标记为默认；多次配置时需明确哪个是默认

### 场景二：工作项继承 workspace 默认模型

**触发条件**：工作项的 `setting.json` 中 `provider` 和 `model` 均为 `null`，
执行 `yzrws start` 时。

**期望行为**：自动使用 `<workspace>/.config/provider.json` 中标记为 `default` 的 Provider。

**困难与挑战**：

- 回退链需要清晰定义：workitem → workspace 默认 → 引擎内置默认值
- workspace 内 `default` 字段被清空时，需要回退到首个 Provider 或提示用户

### 场景三：工作项覆盖 workspace 默认

**触发条件**：工作项的 `setting.json` 中显式指定了 `provider` 或 `model`。

**期望行为**：使用工作项自己的配置，不受 workspace 默认影响。

**困难与挑战**：

- 需要区分"显式设为 null"和"从未设置"——当前设计中 `null` 统一表示"继承上层"
- 用户可能需要一种方式"恢复继承"（将显式值改回 null）

### 场景四：管理多个 Provider

**触发条件**：用户配置了多个 Provider（如不同服务商、不同模型），需要查看 / 切换 / 删除。

**期望行为**：支持 list（列出全部）、remove（删除）、set-default（切换默认）操作。

**困难与挑战**：

- 删除一个被工作项引用的 Provider 时需要警告
- 删除默认 Provider 后 `default` 字段置空，提示用户设置新的默认

### 场景五：BaseURL 与 engine 类型不匹配

**触发条件**：同一个 model 名（如 `claude-sonnet-4-6`）可能出现在不同 Provider 中，
但其 `base_url` 只适配某一种 engine（如 Anthropic 官方 API 给 claude-code 用，
某 OpenAI 兼容网关给 opencode 用）；workitem 选中了与自身 engine 不兼容的 Provider。

**期望行为**：

- 添加 Provider 时可显式标注 `agent_types`（`["claude-code"]` / `["opencode"]` /
  `["claude-code", "opencode"]`），缺省时兼容所有已注册 engine
- `yzrws workitem set-model` 选中不兼容的 provider 时**报错**退出码 1（防止误配）
- `yzrws start` 临时通过 `--engine` 切换到不兼容的 engine 时仅打印 **WARN**，不阻止启动
  （允许用户显式尝试）

**困难与挑战**：

- 同一 model 名跨多个 Provider 出现时，需要在 workitem 层面做 engine 兼容性检查，
  而不是只看 model 字符串
- `agent_types` 缺省时的"全部兼容"语义需要与 `engine.list_engines()` 联动，避免
  引入新 engine 后还要改旧 provider.json

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 配置默认模型 | 交互式 add 命令 | 敏感信息输入、格式校验 | §创建流程 / §Provider Schema |
| 继承 workspace 默认 | workitem provider 为 null | 回退链优先级 | §回退链 |
| 覆盖 workspace 默认 | workitem 显式指定 provider | null 语义统一 | §回退链 |
| 管理多个 Provider | list / remove / set-default | 删除保护、默认切换 | §管理命令 |
| BaseURL 与 engine 不匹配 | workitem 选中的 provider agent_types 不包含 workitem engine | set-model 防误配 / start 允许临时尝试 | §Provider Schema / §管理命令 |

## 方案选择

### 备选方案

#### 方案 A：仅 workspace 级配置

Provider 统一存放在 `<workspace>/.config/provider.json`，跨 workspace 不共享。

- 收益：实现简单，无多层合并问题；敏感凭据与 workspace 绑定，避免泄露到用户级
- 代价：每个 workspace 需要重复配置相同 Provider（如个人常用服务商）

#### 方案 B：用户级 + Workspace 级双层配置

Provider 同时支持用户级（`~/.config/yzrws/provider.json`）和 workspace 级，workitem 按回退链查找。

- 收益：灵活，workspace 可以有专属的模型配置；用户级配置作为通用兜底
- 代价：需要处理多层合并和优先级；实现复杂度中等；Auth Key 跨 workspace 流转有泄露风险

#### 方案 C：不处理（基线）

不实现 Provider 管理命令，让用户手动编辑 JSON 文件。

- 适用于：只有一个 Provider、不需要切换的场景

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| 配置位置 | workspace 单层 | 双层合并 | 手动 |
| 多 Provider 管理 | 命令管理 | 命令管理 | 手动编辑 |
| 回退链 | 单层 | 多层 | 无 |
| 凭据隔离 | 强（每 workspace 独立） | 弱（用户级跨 workspace） | 由用户控制 |
| 实现复杂度 | 低 | 中等 | — |

### 推荐方案

推荐方案 A。

理由：

1. yzrws 工具的核心是"为每个工作项隔离可沉淀的工作环境"，Provider 属于工作环境的一部分
2. 用户级 Provider 配置在多 workspace 场景下容易产生"上次配置的是哪个 workspace"的混淆
3. Auth Key 等敏感凭据应与 workspace 同生命周期，便于清理 / 迁移
4. 实现简单，行为可预测——所有 Provider 命令的"目标文件"始终唯一
5. 若用户需要在多个 workspace 间共享，可借助文件系统软链接 / 模板工具手动管理

### 否决理由

- **方案 B**：双层配置在多 workspace 场景下增加心智负担（每次 `list` 都要合并两层），
  且 Auth Key 跨 workspace 流转有泄露风险
- **不处理**：手动编辑 JSON 容易出错，且缺乏删除保护和默认切换能力

## Provider Schema

### 配置文件结构

Provider 配置文件始终位于：

```text
<workspace>/.config/provider.json
```

```jsonc
// provider.json
{
  "providers": {
    "anthropic": {
      "base_url": "https://api.anthropic.com",
      "auth_key": "sk-ant-xxxxx",
      "model": "claude-sonnet-4-6",
      "agent_types": ["claude-code", "opencode"]   // 可选：缺省时兼容所有已注册 engine
    },
    "my-gateway": {
      "base_url": "https://gw.mycompany.com/v1",
      "auth_key": "company-token-xxxxx",
      "model": "gpt-4o",
      "agent_types": ["opencode"]                 // 仅 OpenCode 能消费
    }
  },
  "default": "anthropic"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `providers` | object | ✓ | Provider 注册表，key 为 Provider 名称 |
| `providers.<name>.base_url` | string | ✓ | API 端点地址（合法 URL） |
| `providers.<name>.auth_key` | string | ✓ | 认证密钥（明文存储，用户自行保护文件权限） |
| `providers.<name>.model` | string | ✓ | 默认模型名称 |
| `providers.<name>.agent_types` | list[string] | ✗ | 该 provider 的 `base_url` 适配的 engine 列表；用于防止 workitem 选中与当前 engine 不兼容的 provider。缺省 / 字段缺失时回退到所有已注册 engine（`list_engines()`）。**特殊值** `all` 是 CLI 层的 alias，表示"兼容所有 engine"（与字段缺失等价），不会原样写入 JSON |
| `default` | string | ✗ | 默认 Provider 名称，引用 `providers` 中的 key |

### Provider 命名规则

- 只允许小写字母、数字、连字符（`-`）和下划线（`_`）
- 长度限制：1-32 个字符
- 正则：`^[a-z0-9][a-z0-9_-]{0,31}$`

## 回退链

> **本回退链由 `yzrws workitem set-model` / `yzrws start` 实现消费**：
> `yzrws workitem set-model` 把 Provider 引用写入 `setting.json.provider`；
> `yzrws start` 在启动前调用 `provider.resolve_model_config` 解析生效配置，
> 并把 `(base_url, auth_key, model)` 注入到引擎进程（见
> [`multi_agent_design.md`](./multi_agent_design.md)）。

当 `yzrws start` 启动工作项的 Agent 会话时，按以下优先级确定模型配置：

### 查找顺序

```text
1. workitem setting.json
   └── provider 非 null？→ 使用指定 provider
       model 非 null？  → 使用指定 model
                          │
2. workspace provider.json（<workspace>/.config/provider.json）
   └── default 字段指向的 Provider → 使用该 Provider 的 model / auth_key / base_url
                          │
3. 引擎内置默认值
   └── Claude Code: Anthropic 官方 API
       OpenCode: 无内置默认值，必须由 1-2 提供
```

### 字段级 vs 整体级

回退是**整体级**的——如果 workitem 指定了 `provider`，则使用该 provider 的全部字段
（`base_url` / `auth_key` / `model`），不会从上层"补全"缺失字段。
workitem 的 `model` 字段**不允许**单独覆盖 provider 的 `model`——`yzrws workitem
set-model` 只接受 `--provider` 参数；如需切换 model，请添加新的 Provider 后重新
`set-model --provider <new-name>`。

### 回退链示例

```text
工作项 A: setting.json = { provider: null, model: null }
  → 回退到 workspace provider.json 的 default

工作项 B: setting.json = { provider: "my-gateway", model: null }
  → 使用 "my-gateway" 的 base_url / auth_key / model
```

## 创建流程

### yzrws model provider add

交互式添加 Provider：

```text
yzrws model provider add
  │
  ├── 1. 前置检查
  │     └── workspace 已初始化？
  │
  ├── 2. 交互式输入
  │     ├── Provider 名称：[提示输入，校验命名规则]
  │     ├── Base URL：[提示输入，校验 URL 格式]
  │     ├── Auth Key：[提示输入，隐藏回显]
  │     └── Model name：[提示输入]
  │
  ├── 3. 写入 provider.json
  │     ├── 如果文件不存在 → 创建并写入
  │     ├── 如果同名 Provider 已存在 → 提示确认覆盖
  │     └── 如果是首个 Provider → 自动标记为 default
  │
  └── 4. 输出确认
        └── 列出新增的 Provider 信息（Auth Key 脱敏显示）
```

### 交互示例

```sh
$ yzrws model provider add

=== 添加 Provider ===

目标文件：/Users/<user>/yzr_workspace/.config/provider.json

Provider 名称: anthropic
Base URL: https://api.anthropic.com
Auth Key: ********************************
Model name: claude-sonnet-4-6

  [新增] Provider 'anthropic'
  [默认] 首个 Provider，已自动设为默认

=== 添加成功 ===
```

**Agent types 交互式 prompt**（在 `--agent-type` 未指定时出现）：

```text
Agent types:
  1) all（兼容所有 engine）
  2) claude-code
  3) opencode
请选择（逗号分隔多个，回车默认 1）: _
```

接受的输入：

- 留空 / `1` → 兼容所有 engine（与不指定等价）
- `2` / `3` / `2,3` → 限定具体子集
- `all`（编号 1）与具体 engine 混用 → 拒绝（语义模糊）
- 编号超出范围 / 非数字 → 拒绝并提示

### 非交互模式

所有字段均可通过 CLI 参数传入（适合脚本化）：

```sh
yzrws model provider add \
  --name anthropic \
  --base-url https://api.anthropic.com \
  --auth-key sk-ant-xxxxx \
  --model claude-sonnet-4-6

# 限定 agent_types（缺省时兼容所有已注册 engine）
yzrws model provider add \
  --name my-gateway \
  --base-url https://gw.company.com/v1 \
  --auth-key company-token \
  --model gpt-4o \
  --agent-type opencode

# 显式声明兼容所有 engine（与不传 --agent-type 等价；补全里可发现）
yzrws model provider add \
  --name anthropic-all \
  --base-url https://api.anthropic.com \
  --auth-key sk-ant-xxxxx \
  --model claude-sonnet-4-6 \
  --agent-type all
```

## 管理命令

### yzrws model provider list

列出所有已配置的 Provider：

```sh
$ yzrws model provider list

=== Provider 列表 ===

NAME       BASE_URL                     MODEL               AGENT_TYPES
----------  ---------------------------  ------------------  ----------------
anthropic   https://api.anthropic.com    claude-sonnet-4-6   all
my-gateway  https://gw.company.com/v1    gpt-4o              opencode
```

- `★ 默认` 标注当前生效的默认 Provider
- `AGENT_TYPES` 列显示该 provider 适配的 engine 列表；值为 `all` 时表示
  `agent_types` 缺省（兼容所有已注册 engine）
- Auth Key 不显示（安全）

### yzrws model provider remove

删除指定 Provider：

```sh
yzrws model provider remove <name> [-y]
```

删除保护：

- 如果被删除的 Provider 是默认 Provider → 提示该层 default 将被清空
- 如果被删除的 Provider 被某个工作项的 `setting.json` 引用 → 输出警告（不阻止删除）

### yzrws model provider set-default

切换默认 Provider：

```sh
yzrws model provider set-default <name>
```

指定的 Provider 必须存在于 `<workspace>/.config/provider.json`。

## 前置检查

Provider 命令依赖 workspace 已初始化（`<workspace>/metadata.json` 存在）：

| 检查项 | 缺失时行为 |
| --- | --- |
| `<workspace>/.config/` 目录 | 报错：提示执行 `yzrws init` |
| `<workspace>/metadata.json` | 报错：提示执行 `yzrws init` |

## 命令接口

### 命令格式汇总

```sh
# 添加
yzrws model provider add [--name ... --base-url ... --auth-key ... --model ...] [--agent-type <engine>]... [--set-default] [-y]

# 列出
yzrws model provider list

# 删除
yzrws model provider remove <name> [-y]

# 设置默认
yzrws model provider set-default <name>
```

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `<name>` | remove / set-default 必须 | Provider 名称 |
| `--name` / `--base-url` / `--auth-key` / `--model` | ✗ | add 子命令的非交互参数；缺省时进入交互式输入 |
| `--agent-type` | ✗ | add 时指定 provider 兼容的 engine（可多次）；缺省或传值 `all` 时表示兼容所有已注册 engine。`all` 不能与具体 engine 混用 |
| `--set-default` | ✗ | add 时强制将新 Provider 设为默认 |
| `-y` / `--yes` | ✗ | add / remove 时跳过确认 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 操作成功 |
| 1 | 操作失败（名称不合法、Provider 不存在、workspace 未初始化等） |

## 文件归属

| 文件 | 说明 | 纳入版本控制 |
| --- | --- | --- |
| `src/yzrws/provider.py` | Provider 管理业务逻辑 | ✓ |
| `src/yzrws/commands/model.py` | `model` 子命令 dispatcher | ✓ |
| `src/yzrws/commands/provider.py` | Provider 4 个子命令 handler | ✓ |
| `<workspace>/.config/provider.json` | Workspace 级 Provider 配置 | 由用户决定 |

> `provider.json` 包含 Auth Key 等敏感信息。
> 如果 workspace 纳入版本控制，建议将 `.config/provider.json` 加入 `.gitignore`。

## 与其他文档的关系

- [`multi_agent_design.md`](./multi_agent_design.md)：`setting.json` 的 `provider` 字段引用本文档的 Provider 名称
- [`workitem_create_design.md`](./workitem_create_design.md)：创建时 `provider` 为 `null`，
  运行时按本文档的回退链查找
- [`metadata_design.md`](./metadata_design.md)：Provider 配置不属于 `metadata.json` 的职责范围
- [`command_design.md`](./command_design.md)：本文档定义了 `yzrws model provider` 子命令集的完整设计
