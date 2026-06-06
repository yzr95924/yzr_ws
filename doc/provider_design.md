# Provider 配置设计

## 概述

Provider 是模型服务商的连接信息（Base URL、Auth Key、模型名称等）的封装。
`yzrws` 支持在两个层级配置 Provider：

- **用户级**（`~/.config/yzrws/provider.json`）：跨 workspace 共享，适合个人常用的服务商
- **Workspace 级**（`<workspace>/.config/provider.json`）：与 workspace 绑定，
  适合项目 / 团队专属的服务商配置

工作项（workitem）通过 `setting.json` 中的 `provider` 字段引用已配置的 Provider。
未指定时，按回退链自动查找 workspace 级的默认 Provider。

## 场景分析

### 场景一：配置默认模型

**触发条件**：用户首次使用 `yzrws`，或需要为 workspace 设置默认模型。

**期望行为**：通过交互式命令输入 Base URL、Auth Key、Model name，
保存到 workspace 级 `provider.json`，并标记为默认。

**困难与挑战**：

- Auth Key 是敏感信息，交互式输入时不应回显（需隐藏输入）
- 需要验证 Base URL 的格式合法性（至少是合法的 URL）
- 首次配置时自动标记为默认；多次配置时需明确哪个是默认

### 场景二：工作项继承 workspace 默认模型

**触发条件**：工作项的 `setting.json` 中 `provider` 和 `model` 均为 `null`，
执行 `yzrws start` 时。

**期望行为**：自动使用 workspace 级 `provider.json` 中标记为 `default` 的 Provider。

**困难与挑战**：

- 回退链需要清晰定义：workitem → workspace → 用户级 → 引擎内置默认值
- 多层都存在默认 Provider 时，优先级必须明确

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
- 删除默认 Provider 后需要提示用户设置新的默认

### 场景五：workspace 级与用户级同名 Provider

**触发条件**：workspace 级和用户级 `provider.json` 中都配置了同名的 Provider。

**期望行为**：workspace 级优先，覆盖用户级同名配置。

**困难与挑战**：

- 需要明确"覆盖"是字段级还是整体级——推荐整体覆盖（workspace 级同名 Provider 整体替代用户级）
- 用户需要能感知到覆盖关系（list 时标注来源）

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 配置默认模型 | 交互式 add 命令 | 敏感信息输入、格式校验 | §创建流程 / §Provider Schema |
| 继承 workspace 默认 | workitem provider 为 null | 多层回退链优先级 | §回退链 |
| 覆盖 workspace 默认 | workitem 显式指定 provider | null 语义统一 | §回退链 |
| 管理多个 Provider | list / remove / set-default | 删除保护、默认切换 | §管理命令 |
| 同名覆盖 | workspace 与用户级同名 | 覆盖粒度 | §多层合并 |

## 方案选择

### 备选方案

#### 方案 A：仅用户级配置

Provider 只存在 `~/.config/yzrws/provider.json`，所有 workspace 共享。

- 收益：实现简单，无多层合并问题
- 代价：无法为不同 workspace 设置不同默认模型；
  个人和项目的 API Key 混在一起

#### 方案 B：用户级 + Workspace 级双层配置

Provider 同时支持用户级和 workspace 级，workitem 按回退链查找。

- 收益：灵活，workspace 可以有专属的模型配置；
  用户级配置作为通用兜底
- 代价：需要处理多层合并和优先级；实现复杂度中等

#### 方案 C：不处理（基线）

不实现 Provider 管理命令，让用户手动编辑 JSON 文件。

- 适用于：只有一个 Provider、不需要切换的场景

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| workspace 专属配置 | 不支持 | 支持 | 不支持 |
| 多 Provider 管理 | 手动编辑 | 命令管理 | 手动编辑 |
| 回退链 | 单层 | 多层（workitem → workspace → 用户级） | 无 |
| 删除 / 切换默认 | 手动编辑 | 命令操作 | 手动编辑 |
| 实现复杂度 | 低 | 中等 | — |

### 推荐方案

推荐方案 B。

理由：

1. 不同 workspace 使用不同模型是常见需求——如个人项目用 Anthropic API，
   公司项目用内部网关
2. workspace 级配置让模型信息与项目绑定，便于团队协作（可以提交到版本控制或排除）
3. 用户级配置作为兜底，减少重复配置
4. 中等复杂度可控，回退链逻辑与已有的引擎选择策略一致

### 否决理由

- **方案 A**：无法为不同 workspace 设置不同默认模型，
  当用户同时有个人和公司项目时不够灵活
- **不处理**：手动编辑 JSON 容易出错，且缺乏删除保护和默认切换能力

## Provider Schema

### 配置文件结构

Provider 配置文件存储在两个位置，格式完全一致：

```text
~/.config/yzrws/provider.json              # 用户级（跨 workspace 共享）
<workspace>/.config/provider.json           # Workspace 级（与 workspace 绑定）
```

```jsonc
// provider.json
{
  "providers": {
    "anthropic": {
      "base_url": "https://api.anthropic.com",
      "auth_key": "sk-ant-xxxxx",
      "model": "claude-sonnet-4-6"
    },
    "my-gateway": {
      "base_url": "https://gw.mycompany.com/v1",
      "auth_key": "company-token-xxxxx",
      "model": "gpt-4o"
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
| `default` | string | ✗ | 默认 Provider 名称，引用 `providers` 中的 key |

### Provider 命名规则

- 只允许小写字母、数字、连字符（`-`）和下划线（`_`）
- 长度限制：1-32 个字符
- 正则：`^[a-z0-9][a-z0-9_-]{0,31}$`

## 回退链

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
3. 用户级 provider.json（~/.config/yzrws/provider.json）
   └── default 字段指向的 Provider → 使用该 Provider 的 model / auth_key / base_url
                          │
4. 引擎内置默认值
   └── Claude Code: Anthropic 官方 API
       OpenCode: 无内置默认值，必须由 1-3 提供
```

### 字段级 vs 整体级

回退是**整体级**的——如果 workitem 指定了 `provider`，则使用该 provider 的全部字段
（`base_url` / `auth_key` / `model`），不会从上层"补全"缺失字段。

例外：workitem 的 `model` 可以单独覆盖 provider 的 `model` 字段。
例如 `provider` 指向 `anthropic`（默认 `claude-sonnet-4-6`），
但 `model` 显式设为 `claude-opus-4-8`，则使用 Opus 模型。

### 回退链示例

```text
工作项 A: setting.json = { provider: null, model: null }
  → 回退到 workspace provider.json 的 default
  → 如果 workspace 无 provider.json → 回退到用户级 provider.json 的 default

工作项 B: setting.json = { provider: "my-gateway", model: null }
  → 使用 "my-gateway" 的 base_url / auth_key / model

工作项 C: setting.json = { provider: "anthropic", model: "claude-opus-4-8" }
  → 使用 "anthropic" 的 base_url / auth_key，但 model 覆盖为 opus
```

## 多层合并

当 workspace 级和用户级 `provider.json` 都存在时：

### 合并规则

- **同名 Provider**：workspace 级整体覆盖用户级（不是字段级合并）
- **不同名 Provider**：两者都可用，workitem 可以引用任意一层的 Provider
- **default**：workspace 级的 `default` 优先于用户级的 `default`

### 合并示例

```jsonc
// 用户级 ~/.config/yzrws/provider.json
{
  "providers": {
    "anthropic": { "base_url": "https://api.anthropic.com", "auth_key": "sk-ant-xxx", "model": "claude-sonnet-4-6" },
    "openai": { "base_url": "https://api.openai.com/v1", "auth_key": "sk-xxx", "model": "gpt-4o" }
  },
  "default": "anthropic"
}

// Workspace 级 <workspace>/.config/provider.json
{
  "providers": {
    "anthropic": { "base_url": "https://proxy.company.com/anthropic", "auth_key": "company-xxx", "model": "claude-sonnet-4-6" }
  },
  "default": "anthropic"
}

// 合并结果：
// - anthropic: 使用 workspace 级（公司代理）
// - openai: 使用用户级（个人账号）
// - default: anthropic（workspace 级优先）
```

## 创建流程

### yzrws model provider add

交互式添加 Provider：

```text
yzrws model provider add
  │
  ├── 1. 确定配置层级
  │     └── 默认写入 workspace 级（<workspace>/.config/provider.json）
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

Provider 名称: anthropic
Base URL: https://api.anthropic.com
Auth Key: ********************************
Model name: claude-sonnet-4-6

  [新增] Provider "anthropic"
  [默认] 已设为默认 Provider

=== 添加成功 ===
```

### 配置层级选择

默认写入 workspace 级。如果用户想配置用户级（跨 workspace 共享），
使用 `--global` 参数：

```sh
# 写入 workspace 级（默认）
yzrws model provider add

# 写入用户级
yzrws model provider add --global
```

## 管理命令

### yzrws model provider list

列出所有已配置的 Provider（含来源标注）：

```sh
$ yzrws model provider list

=== Provider 列表 ===

  [workspace] anthropic        https://api.anthropic.com           claude-sonnet-4-6     ★ 默认
  [global]    openai           https://api.openai.com/v1           gpt-4o
  [workspace] my-gateway       https://gw.company.com/v1           gpt-4o
```

- `[workspace]` / `[global]` 标注来源
- `★ 默认` 标注当前生效的默认 Provider
- Auth Key 不显示（安全）

### yzrws model provider remove

删除指定 Provider：

```sh
yzrws model provider remove <name> [--global]
```

删除保护：

- 如果被删除的 Provider 是默认 Provider → 提示先设置新的默认
- 如果被删除的 Provider 被某个工作项的 `setting.json` 引用 → 输出警告（不阻止删除）
- 如果 workspace 级和用户级都有同名 Provider → 默认删除 workspace 级，
  使用 `--global` 删除用户级

### yzrws model provider set-default

切换默认 Provider：

```sh
yzrws model provider set-default <name> [--global]
```

- 默认设置 workspace 级的 `default` 字段
- 使用 `--global` 设置用户级的 `default` 字段
- 指定的 Provider 必须在对应层级存在

## 前置检查

Provider 命令的 workspace 级操作依赖 workspace 已初始化：

```text
检查项                                     缺失时行为
────────────────────────────────────────────────────
~/yzr_workspace/.config/ 目录               报错：提示执行 yzrws init
```

`--global` 操作不依赖 workspace，直接写入 `~/.config/yzrws/provider.json`。
如果 `~/.config/yzrws/` 目录不存在，自动创建。

## 命令接口

### 命令格式汇总

```sh
# 添加
yzrws model provider add [--global]

# 列出
yzrws model provider list

# 删除
yzrws model provider remove <name> [--global]

# 设置默认
yzrws model provider set-default <name> [--global]
```

| 参数 | 是否必须 | 说明 |
| --- | --- | --- |
| `<name>` | remove / set-default 必须 | Provider 名称 |
| `--global` | ✗ | 操作用户级配置而非 workspace 级 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 操作成功 |
| 1 | 操作失败（名称不合法、Provider 不存在、workspace 未初始化等） |

## 文件归属

| 文件 | 说明 | 纳入版本控制 |
| --- | --- | --- |
| `scripts/python/provider.py` | Provider 管理逻辑 | ✓ |
| `~/.config/yzrws/provider.json` | 用户级 Provider 配置 | 否（用户级） |
| `<workspace>/.config/provider.json` | Workspace 级 Provider 配置 | 由用户决定 |

> Workspace 级 `provider.json` 包含 Auth Key 等敏感信息。
> 如果 workspace 纳入版本控制，建议将 `.config/provider.json` 加入 `.gitignore`。

## 与其他文档的关系

- [`multi_agent_design.md`](./multi_agent_design.md)：`setting.json` 的 `provider` 字段引用本文档的 Provider 名称
- [`workitem_create_design.md`](./workitem_create_design.md)：创建时 `provider` 为 `null`，
  运行时按本文档的回退链查找
- [`metadata_design.md`](./metadata_design.md)：Provider 配置不属于 `metadata.json` 的职责范围
- [`command_design.md`](./command_design.md)：本文档定义了 `yzrws model provider` 子命令集的完整设计
