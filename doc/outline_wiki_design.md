# Outline Wiki MCP 接入设计

## 概述

`yzrws` 把每个工作项（workitem）包装成一个可恢复、可沉淀的 Code Agent 会话。
本设计把 Outline Wiki 暴露的 [MCP（Model Context Protocol）](https://modelcontextprotocol.io)
服务接入到工作项中——让工作项的 Code Agent 启动时自动加载 Outline MCP，
从而能够直接检索、读取、创建、修改 Outline 上的文档。

核心决策（已与用户确认）：

- **Workspace 级单 endpoint**：workspace 下只维护一份 Outline 连接配置，
  存放在 `<workspace>/.config/outline.json`。
- **Workitem 引用式启用**：workitem 通过 `setting.json.outline` 字段以字符串
  形式引用 workspace 的配置（`"default"`），`null` / 字段缺失表示不启用。
  语义与 [`provider_design.md`](./provider_design.md) 的 `provider` 字段对齐。
- **API key 明文存储**：与 `provider.json` 的 `auth_key` 风格一致，敏感文件
  建议加入 `.gitignore`，yzrws 不引入额外密钥管理机制。

Outline 官方 MCP 服务仅支持 **Streamable HTTP** 传输，固定路径为
`/mcp`，认证方式为 `Authorization: Bearer <api-key>` Header。
yzrws 端不实现 OAuth 流程——只支持"在 Outline 后台生成 API key"的认证方式。

## 场景分析

### 场景一：首次配置 Outline 连接

**触发条件**：用户首次需要让工作项中的 Code Agent 访问 Outline Wiki，
工作区已通过 `yzrws init` 初始化。

**期望行为**：通过 `yzrws outline add` 交互式输入 Outline 实例 URL
（如 `https://<subdomain>.getoutline.com`）与 API key，
写入 `<workspace>/.config/outline.json`；之后所有引用该配置的工作项
在 `yzrws start` 时自动加载 Outline MCP。

**困难与挑战**：

- API key 是敏感信息，交互式输入时需要隐藏回显（沿用 `provider add` 的
  `getpass.getpass` 方案）
- URL 格式校验：必须是合法 HTTPS URL（Outline 官方强制 HTTPS；
  自托管场景若用户使用 HTTP 反代需自己承担风险）
- URL 末尾是否含 `/mcp` 路径需要规范化——yzrws 内部统一存"裸 endpoint"，
  注入引擎时自动拼 `/mcp`
- 需要提示用户"如何在 Outline 后台生成 API key"
  （**Settings → API → Create API key**），避免用户走 OAuth 路线

### 场景二：工作项引用 workspace 配置

**触发条件**：用户在某 workitem 的 `setting.json` 中将 `outline` 字段
设为 `"default"`，或运行 `yzrws workitem set-outline <name>`。

**期望行为**：`yzrws start <name>` 启动前，yzrws 读取
`<workspace>/.config/outline.json`，把 `(endpoint, auth_token)`
注入到对应引擎的原生 MCP 配置位置（Claude Code 的 `.mcp.json` /
OpenCode 的 `opencode.json` 的 `mcp` 字段），Code Agent 启动后即可调用
Outline 提供的 MCP 工具。

**困难与挑战**：

- 两个引擎的 MCP 配置格式不同，需要在 `engine/` 适配器中分别处理
- 桥接文件需要原子写入，写失败时不污染已有内容
- 需要在 `.gitignore` 中加入桥接文件，避免敏感 token 入库
- 启动时若 outline.json 缺失或字段损坏，需要降级处理——打印 WARN
  并以"未启用 Outline MCP"行为启动（**不**失败阻塞）

### 场景三：工作项不引用（默认行为）

**触发条件**：workitem 的 `setting.json` 中 `outline` 字段为 `null`
或字段缺失。

**期望行为**：`yzrws start` 启动前不生成任何 MCP 桥接文件，
引擎按"未配置 Outline MCP"行为启动。

**困难与挑战**：

- 需要沿用 provider 的"null = 继承上层"语义——但 outline 没有"上层默认"概念，
  直接视为"不启用"。`null` 与"从未设置"在本设计中行为一致，无需区分
- 如果 workitem 的 `outline` 字段意外指向不存在的 endpoint 名称
  （如 `"production"`），启动时应打印 WARN 并跳过，而非 crash

### 场景四：更新 API key 或 URL

**触发条件**：用户在 Outline 后台轮换了 API key，或迁移到了另一个
Outline 实例（自托管域名变更）。

**期望行为**：`yzrws outline update [--endpoint ...] [--auth-token ...]`
对 `<workspace>/.config/outline.json` 做原地更新；
下次 `yzrws start` 即生效（无需重建 workitem）。

**困难与挑战**：

- 至少要更新一个字段，全空时提示用法
- API key 字段更新时需要二次确认（敏感操作）
- 不需要扫描引用——所有引用 `"default"` 的 workitem 都会自动用新值
  （这是"单 endpoint 引用式"的天然好处）

### 场景五：删除配置

**触发条件**：用户不再需要 Outline 集成，执行 `yzrws outline remove`。

**期望行为**：删除 `<workspace>/.config/outline.json`；
扫描 workspace 下所有 workitem 的 `setting.json`，对 `outline` 字段
引用过该配置的 workitem 输出警告（不修改、不阻塞）。

**困难与挑战**：

- 警告要列出所有受影响的 workitem 名称，方便用户批量处理
- 建议用户对受影响 workitem 执行 `yzrws workitem unset-outline <name>`
  以"显式关闭"，避免后续 outline.json 重建后被自动恢复
- 配置文件不存在时是幂等成功（不报错）

### 场景六：引擎切换时的 MCP 重写

**触发条件**：workitem 在不同会话中切换 `engine`（如
`yzrws start my-task --engine opencode`，而 `setting.json.engine`
原本是 `claude-code`）。

**期望行为**：启动时按**当前生效**的引擎重新生成 MCP 桥接文件；
旧引擎的桥接文件（如 `.mcp.json` 在切换到 opencode 后）由适配器
按需清理（保留无害但避免遗留敏感 token）。

**困难与挑战**：

- 切换引擎时已经会归档旧 session，本设计复用这个时点清理旧桥接文件
- 同一 workitem 内不应同时存在 `.mcp.json` 与 `opencode.json` 的 mcp 字段
  残留，否则切换回原引擎时可能误读

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 首次配置 | `outline add` | API key 隐藏、URL 规范化、引导生成 key | §配置文件 Schema / §添加命令 |
| 工作项引用 | `set-outline` / setting.json `outline="default"` | 引擎适配、原子写入、降级行为 | §引擎适配 / §启动集成 |
| 不引用 | `outline: null` / 字段缺失 | null 语义、不存在的引用名处理 | §引用语义 / §启动集成 |
| 更新配置 | `outline update` | 至少一个字段、二次确认 | §更新命令 |
| 删除配置 | `outline remove` | 引用扫描、幂等 | §删除命令 |
| 引擎切换 | `start --engine` 切换 | 旧桥接文件清理 | §引擎适配 / §启动集成 |

## 方案选择

### 备选方案

#### 方案 A：单 endpoint + 引用式（推荐）

workspace 下 `<workspace>/.config/outline.json` 存一份 endpoint，
workitem 的 `setting.json.outline` 字段是字符串（`"default"` / `null`）。

- 收益：与 provider 模式同构（"引用一个名字，名字解析为端点 + 凭据"），
  心智模型统一；单 endpoint 满足 99% 场景（个人 + 公司二选一），
  实现简单；引用名固定为 `"default"` 即可
- 代价：不支持"云端 + 自托管并存"；未来若要多 endpoint 需要小改 schema

#### 方案 B：多 endpoint + 引用式

workspace 可配置多个 endpoint（结构同 provider 的 `providers`），
workitem 引用其中一个。

- 收益：可同时挂多个 Outline 实例（如同时连团队 wiki 和个人 wiki）
- 代价：实现复杂度上升；绝大多数用户用不到

#### 方案 C：不处理（基线）

yzrws 不提供 Outline MCP 集成，用户自己编辑
`<workitem>/.mcp.json`（Claude Code）或
`<workitem>/opencode.json`（OpenCode）。

- 适用于：极少使用 Outline、且愿意手动维护 MCP 配置的场景
- 代价：违反 yzrws "工作环境自动化封装"的定位；用户每次新建 workitem
  都要重新接 MCP

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| 引用语义 | ✓ 字符串引用 | ✓ 字符串引用 | 手动 |
| 多 endpoint | ✗ | ✓ | — |
| 引擎适配 | 统一处理 | 统一处理 | 用户手动 |
| 与 provider 模式一致性 | 高 | 高 | 低 |
| 实现复杂度 | 低 | 中 | — |
| 未来扩展性 | 可平滑升级到 B | — | — |

### 推荐方案

推荐方案 A。

理由：

1. 单 endpoint 满足绝大多数用户的实际场景（个人 / 公司二选一），
   多 endpoint 的需求是"两套账号"叠加，在 yzrws 当前的 1 人维护场景下极少出现
2. 与 `provider.json` 模式同构：用户已经理解"workitem 通过名字引用
   workspace 配置"，outline 复用这套心智模型，零学习成本
3. 未来若用户实际产生多 endpoint 需求，schema 从
   `{endpoint, auth_token}` 升级到 `{outlines: {default: {...}}}` 是
   兼容式扩展（旧的扁平字段可读为 default）
4. 与 `provider_design.md` 一样"所有凭据存于 workspace 级，
   与 workspace 同生命周期"——避免用户级副本带来的歧义

### 否决理由

- **方案 B**：在 yzrws 当前的 1 人维护场景下，"多 Outline 实例"需求极少；
  提前支持会引入额外的命名空间与回退链设计，违背 yzrws "简洁优先"的原则
- **不处理**：手写 `.mcp.json` 需要用户理解每个引擎的 MCP 配置格式，
  且 API key 容易泄露到 git；与 yzrws "工作环境封装" 的定位背离

## 配置文件 Schema

### outline.json

```text
<workspace>/.config/outline.json
```

```jsonc
// <workspace>/.config/outline.json
{
  "endpoint": "https://<subdomain>.getoutline.com", // Outline 实例 URL（不含 /mcp 路径）
  "auth_token": "ol_api_xxxxxxxxxxxxxxxx"            // Outline 后台生成的 API key
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `endpoint` | string | ✓ | Outline 实例 URL，scheme 必须为 `https`，不含尾随 `/` 也不含 `/mcp` 路径 |
| `auth_token` | string | ✓ | Outline API key（明文存储，yzrws 不做加密，由用户自行保护文件权限） |

### 校验规则

- `endpoint`：使用 `urllib.parse.urlparse` 校验，scheme 必须为 `https`，
  必须有 `netloc`（域名 / 端口）
- `auth_token`：非空字符串，长度建议 ≥ 16 字符（不强制，Outline 后台生成的
  key 通常 30+ 字符）
- 启动时若文件缺失或字段损坏，**不**报错——打印 WARN 并以"未启用 Outline
  MCP"行为启动（workitem 引用 `"default"` 也会被忽略）

## 引用语义

### workitem setting.json 扩展

```jsonc
// <workitem>/setting.json
{
  "engine": "claude-code",      // 现有字段，未变化
  "model": null,                // 现有字段，未变化
  "provider": null,             // 现有字段，未变化
  "outline": "default",         // 新增：引用 workspace outline endpoint 的名称
                                // null / 字段缺失 = 不启用 Outline MCP
  "env": {}                     // 现有字段，未变化
}
```

### 有效取值

| 取值 | 含义 |
| --- | --- |
| `"default"` | 引用 workspace 中唯一的 endpoint（启用 Outline MCP） |
| `null` / 字段缺失 | 不启用 Outline MCP |

> 引用名必须等于 `"default"`（与单 endpoint 设计一致）；
> 其他值（如 `"production"`）在启动时按"找不到"处理——打印 WARN 并跳过。

### 与 provider 引用的差异

`outline` 字段在概念上对齐 `provider` 字段，但**没有回退链**——
不存在"workspace default"或"引擎内置默认"。`outline: null`
直接表示"不启用"，不会向上层查找。

## 引擎适配

yzrws 在 `engine/` 适配器接口中新增 `sync_mcp()` 方法，
负责把 workspace 解析出的 MCP 配置写入引擎原生的 MCP 配置位置。

### 协议差异与翻译表

yzrws 内部 `mcp_config` 沿用 MCP 规范自身的 transport 命名
（`stdio` / `sse` / `http`），是引擎中性的统一表示。
`sync_mcp()` adapter 只需翻译以下 3 个差异点：

| 字段 | yzrws 内部 | Claude Code | OpenCode |
| --- | --- | --- | --- |
| 顶层 key | （直接是 mcp_config dict） | `mcpServers` | `mcp` |
| server `type` | `http` | `http` | `remote` |
| 落地文件 | （内存中） | `<workitem>/.mcp.json` | `<workitem>/opencode.json` |

`url` / `headers` / server 名（`outline`）均为透传，不做改动。

> 本节给出的是"协议层差异的全集"——后续新增 MCP server（HTTP-based）
> 时，adapter 通常不需要再改；详见 §"扩展指引：添加新的 MCP 集成"。

### 抽象接口扩展

```python
class AgentEngine(ABC):
    """Agent 引擎抽象基类（在 multi_agent_design.md 基础上扩展）。"""

    name: str  # 引擎标识：claude-code / opencode

    @abstractmethod
    def sync_rules(self, workitem_dir: Path) -> None:
        """将 CLAUDE.md 同步到引擎原生的规则格式。"""

    @abstractmethod
    def sync_mcp(
        self,
        workitem_dir: Path,
        mcp_config: dict | None,
    ) -> None:
        """把 MCP 配置写入引擎原生的 MCP 配置位置。

        参数:
            workitem_dir: 工作项目录
            mcp_config: MCP server 配置字典，格式为
                ``{"<server-name>": {"type": "...", "url": "...", "headers": {...}}}``;
                传入 None 时表示"清理所有 yzrws 注入的 MCP 配置"
        """
```

`yzrws start` 在调用 `sync_rules()` 之后、`start()` 之前调用 `sync_mcp()`；
mcp_config 由 yzrws 从 `<workspace>/.config/outline.json` + workitem
`outline` 字段解析得到。

### 解析逻辑

```text
1. 读取 <workitem>/setting.json.outline
   ├── null / 字段缺失 → mcp_config = None（不启用）
   └── "default" →
       ├── 读取 <workspace>/.config/outline.json
       │     ├── 缺失 / 字段损坏 → 打印 WARN，mcp_config = None
       │     └── 正常 → mcp_config = 见下方 mcp_config 结构
       └── 值不为 "default" → 打印 WARN，mcp_config = None

2. mcp_config 结构（注入到两个引擎时的统一格式）：
   // type 字段沿用 MCP 规范自身的 transport 命名（stdio / sse / http），
   // 引擎 adapter 负责映射到引擎原生取值
   // （OpenCode 把 http 映射为 remote）。
   {
     "outline": {
       "type": "http",
       "url": "<endpoint>/mcp",                  // endpoint 末尾自动拼 /mcp
       "headers": {
         "Authorization": "Bearer <auth_token>"
       }
     }
   }
```

### Claude Code 适配

Claude Code 通过 `<workitem>/.mcp.json` 配置项目级 MCP server。
yzrws 在 `sync_mcp()` 中原子写入该文件（写入用
`tempfile.mkstemp` + `os.replace`，与 provider.json 风格一致）：

```jsonc
// <workitem>/.mcp.json
{
  "mcpServers": {
    "outline": {
      "type": "http",
      "url": "https://<subdomain>.getoutline.com/mcp",
      "headers": {
        "Authorization": "Bearer <auth_token>"
      }
    }
  }
}
```

- `mcp_config` 为 `None` 时：删除 `<workitem>/.mcp.json`（若存在），
  避免遗留敏感 token
- Claude Code 约定式加载项目根目录的 `.mcp.json`，无需额外 CLI 注入

### OpenCode 适配

OpenCode 通过 `<workitem>/opencode.json` 的 `mcp` 字段配置 MCP server
（`opencode.json` 已由 OpenCode 适配器在 `sync_rules()` 中生成，
用于桥接 CLAUDE.md）。`sync_mcp()` 在已存在的 `opencode.json` 基础上
合并 `mcp` 字段：

```jsonc
// <workitem>/opencode.json
{
  "instructions": ["CLAUDE.md"],   // sync_rules 写入
  "mcp": {                          // sync_mcp 写入 / 合并
    "outline": {
      "type": "remote",
      "url": "https://<subdomain>.getoutline.com/mcp",
      "headers": {
        "Authorization": "Bearer <auth_token>"
      }
    }
  }
}
```

- `mcp_config` 为 `None` 时：从 `opencode.json` 中移除 `mcp.outline` 字段
  （保留用户自定义的其他 MCP 配置）
- 合并策略：保留 `opencode.json` 中已有的其他 key，只覆盖
  `mcp.outline` 字段；不破坏用户的手动配置

### 引擎切换时的清理

`yzrws start --engine <engine>` 触发引擎切换时，归档旧 session 之后、
写入新引擎桥接文件之前，旧引擎的 MCP 桥接文件按以下规则处理：

| 旧引擎 | 新引擎 | 处理 |
| --- | --- | --- |
| claude-code | opencode | 删除 `<workitem>/.mcp.json`（若存在） |
| opencode | claude-code | 从 `opencode.json` 中移除 `mcp.outline` 字段（保留其他 mcp 配置） |

## 启动集成

`yzrws start` 启动流程在原 5 步基础上插入 `sync_mcp()` 步骤：

```text
yzrws start <workitem_name>
  │
  ├── 1. 读取 <workitem>/setting.json，确定引擎
  ├── 2. 读取 <workitem>/session.json（如果有）
  ├── 3. 解析 mcp_config（见 §解析逻辑）
  ├── 4. 调用对应适配器的 sync_rules()
  ├── 5. 调用对应适配器的 sync_mcp(workitem_dir, mcp_config)
  ├── 6. 引擎切换清理（如有）
  ├── 7. 调用 start() 或 resume()
  └── 8. 会话结束后，调用 save_session()
```

WARN 行为（不阻塞启动）：

- `outline: "default"` 但 `<workspace>/.config/outline.json` 缺失 / 损坏
- `outline: "<其他值>"` 找不到对应 endpoint
- `auth_token` 字段为空字符串

## 命令集

### yzrws outline 子命令

```text
yzrws outline add     [--endpoint <url>] [--auth-token <token>] [-y]
yzrws outline show
yzrws outline update  [--endpoint <url>] [--auth-token <token>] [-y]
yzrws outline remove  [-y]
```

#### add

首次添加 Outline 配置：

```text
yzrws outline add
  │
  ├── 1. 前置检查
  │     └── workspace 已初始化（<workspace>/metadata.json 存在）
  │
  ├── 2. 收集参数（缺省时进入交互式输入）
  │     ├── endpoint：提示输入 Outline URL，校验 https + 域名
  │     └── auth_token：提示输入 API key，隐藏回显
  │
  ├── 3. 写入 outline.json（原子写）
  │     ├── <workspace>/.config/outline.json 不存在 → 创建并写入
  │     └── 已存在 → 报错：提示使用 `yzrws outline update`
  │
  └── 4. 输出确认（auth_token 脱敏显示）
```

非交互：

```sh
yzrws outline add \
  --endpoint https://my-team.getoutline.com \
  --auth-token ol_api_xxxxxxxxxxxxxxxx
```

#### show

展示当前 Outline 配置（auth_token 脱敏）：

```text
=== Outline 配置 ===

  KEY          VALUE
  -----------  ----------------------------------------------
  endpoint     https://my-team.getoutline.com
  auth_token   ol_api_xx**********xx

配置文件：/Users/<user>/yzr_workspace/.config/outline.json
```

未配置时：

```text
尚未配置 Outline 连接。

提示：执行 yzrws outline add 添加配置
```

#### update

原地更新 endpoint / auth_token（至少一个）：

```text
yzrws outline update --auth-token ol_api_新key
yzrws outline update --endpoint https://new-host.example.com
yzrws outline update --endpoint ... --auth-token ...
```

- 至少传入 `--endpoint` 或 `--auth-token` 之一
- 配置不存在时报错：提示先 `yzrws outline add`
- 更新 `auth_token` 时需要二次确认（敏感操作），`-y` 跳过
- 不扫描引用——所有引用 `"default"` 的 workitem 下次 start 自动用新值

#### remove

删除 Outline 配置 + 引用扫描：

```text
yzrws outline remove
  │
  ├── 1. 校验 <workspace>/.config/outline.json 存在
  │     └── 缺失 → 回显"未配置 Outline"，退出码 0（幂等）
  │
  ├── 2. 二次确认（-y 跳过）
  │
  ├── 3. 扫描 workspace 下所有 workitem 的 setting.json
  │     └── 收集 outline == "default" 的 workitem 名称
  │
  ├── 4. 删除 outline.json
  │
  └── 5. 输出引用警告（不修改 workitem）
```

引用警告示例：

```text
=== 删除 Outline 配置 ===

配置文件：/Users/<user>/yzr_workspace/.config/outline.json
  [删除] outline.json

  [警告] 以下工作项仍引用 Outline 配置（'default'）：
    - api-refactor
    - doc-restructure

  这些工作项下次 yzrws start 时会打印 WARN（outline 配置缺失），
  仍可正常启动但不会加载 Outline MCP。
  如需显式关闭，可执行：
    yzrws workitem unset-outline api-refactor
    yzrws workitem unset-outline doc-refactor
```

### yzrws workitem set-outline / unset-outline

```text
yzrws workitem set-outline <name>     # 绑定到默认 endpoint
yzrws workitem unset-outline <name>   # 解绑（setting.json.outline = null）
```

`set-outline` 仅做轻量写入——把 `setting.json.outline` 设为 `"default"`。
不读取 outline.json（避免在 outline.json 不存在时报错阻塞）。
启动时再统一解析。

`unset-outline` 把 `outline` 字段从 JSON 中移除（语义同 `null`）。

与 `set-model` 的差异：`set-outline` 不涉及兼容性检查
（Outline MCP 是引擎中性的，claude-code 与 opencode 都能消费）。

### 输出示例

`set-outline` 成功：

```text
=== 设置 Workitem Outline 引用 ===

工作项：my-task
引用名称：default

  [设置] setting.json.outline = 'default'

下次 yzrws start my-task 将自动加载 Outline MCP。

=== 设置成功 ===
```

`unset-outline` 成功：

```text
=== 清除 Workitem Outline 引用 ===

工作项：my-task

  [清除] setting.json.outline = null

下次 yzrws start my-task 不再加载 Outline MCP。

=== 清除成功 ===
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（含 add / show / update / remove / set-outline / unset-outline） |
| 1 | 失败（workspace 未初始化、URL 格式非法、配置不存在、JSON 损坏、用户拒绝确认等） |

## 安全与脱敏

- **API key 隐藏输入**：交互式 `add` / `update` 时使用 `getpass.getpass`，
  与 provider add 一致
- **show 脱敏**：`auth_token` 只显示前 8 + 末 2 字符，中间 `*` 填充
- **list / 引用扫描不显示 token**：警告文本中只列 workitem 名称，
  不打印 outline.json 内容
- **桥接文件 .gitignore**：`doc/outline_wiki_design.md` 提示用户
  把 `<workitem>/.mcp.json` 加入 `.gitignore`（含 Bearer token）
- **引擎切换清理**：切换 engine 时主动删除 / 清理旧桥接文件，
  避免 token 在磁盘上长期残留

## 与现有 provider 配置的差异

| 维度 | provider | outline |
| --- | --- | --- |
| 字段数 | 4-5（base_url, auth_key, model, agent_types） | 2（endpoint, auth_token） |
| 引擎兼容性 | 按 `agent_types` 校验 | 引擎中性，无需校验 |
| 回退链 | workitem → workspace default → 引擎内置 | 无回退链，null = 不启用 |
| 注入目标 | 环境变量 / `opencode.json.model` | 引擎原生 MCP 桥接文件 |
| 多实例支持 | ✓ | ✗（单 endpoint） |
| Workitem 引用字段 | `provider` | `outline` |

> 字段数少 + 无回退链 + 无兼容性检查 = outline 命令比 provider 命令更轻量。

## 文件归属

| 文件 | 说明 | 纳入版本控制 |
| --- | --- | --- |
| `src/yzrws/outline.py` | Outline 配置管理业务逻辑 | ✓ |
| `src/yzrws/commands/outline.py` | `outline` 4 个子命令 handler | ✓ |
| `src/yzrws/commands/workitem.py` | `set-outline` / `unset-outline` handler（与 `set-model` 同模块） | ✓ |
| `src/yzrws/engine/base.py` | 抽象基类新增 `sync_mcp()` 方法签名 | ✓ |
| `src/yzrws/engine/claude_code.py` | `sync_mcp()` 实现：原子写 `<workitem>/.mcp.json` | ✓ |
| `src/yzrws/engine/opencode.py` | `sync_mcp()` 实现：合并 `opencode.json` 的 `mcp.outline` 字段 | ✓ |
| `<workspace>/.config/outline.json` | workspace 级 Outline 配置（含 API key） | ✗（建议 .gitignore） |
| `<workitem>/.mcp.json` | Claude Code MCP 桥接文件 | ✗（建议 .gitignore） |
| `<workitem>/opencode.json` | OpenCode 桥接文件（`instructions` + `mcp`） | ✗（已有约定） |

> 包含 API key 的文件（`outline.json` / `.mcp.json`）均不纳入版本控制；
> 建议用户在 workspace 根目录的 `.gitignore` 中加入：
> `.config/outline.json` 与 `*/.mcp.json`。
> `opencode.json` 沿用 [`multi_agent_design.md`](./multi_agent_design.md) 的
> "不纳入 git" 约定。

## 与其他文档的关系

- [`provider_design.md`](./provider_design.md)：outline 与 provider 是
  "workspace 级凭据 + workitem 引用"模式的一对姊妹；outline 字段数更少、
  无回退链，命令集比 provider 轻量
- [`multi_agent_design.md`](./multi_agent_design.md)：引擎抽象接口
  扩展 `sync_mcp()` 方法；`setting.json` 新增 `outline` 字段；
  `opencode.json` 桥接逻辑扩展为同时包含 `instructions` 和 `mcp` 字段
- [`workitem_create_design.md`](./workitem_create_design.md)：
  `setting.json` 模板新增 `"outline": null` 字段；
  命名规则保持不变（`outline` 是 setting 内部字段，与目录名无关）
- [`command_design.md`](./command_design.md)：定义
  `yzrws outline` 与 `yzrws workitem set-outline / unset-outline` 的
  命令骨架，本文档是其细化
- [`session_design.md`](./session_design.md)：引擎切换时归档旧 session 的
  时点复用为"清理旧 MCP 桥接文件"的时点
- [`workspace_init_design.md`](./workspace_init_design.md)：
  `yzrws init` 不强制创建 `outline.json`——它是"按需配置"，不初始化

## 扩展指引：添加新的 MCP 集成

本设计抽象的 `mcp_config` 内部表示是 MCP-server-通用的——沿用 MCP 规范的
transport 命名（`stdio` / `sse` / `http`），server 名作为 dict 的 key。
`sync_mcp()` adapter 只做 §"协议差异与翻译表" 中的 3 个字符串翻译，
与具体 MCP server 实现无关。

新增 Notion / Slack / 自建 MCP server 的步骤：

1. **workspace 配置**：新建 `<workspace>/.config/<service>.json`，
   字段按 service 自身需求设计（参考 `outline.json` 的最小化风格），
   敏感凭据存明文
2. **workitem 引用**：`setting.json` 新增 `<service>: "default"` 字段
   （与 `outline` 同形；`null` / 字段缺失 = 不启用）
3. **解析逻辑**：在 §"启动集成" 中追加一步
   "读 `<service>.json` → 构造 mcp_config entry"，复用 §"解析逻辑" 的
   模板（先读 setting → 再读 workspace 配置 → 校验 → 拼成 dict）
4. **引擎 adapter**：HTTP-based MCP server **不需要** 改 adapter——
   mcp_config 是 dict 透传，新 server 仅作为
   `<workitem>/.mcp.json` / `opencode.json` 中多出一个 entry
5. **命令集**：参考 `yzrws outline add / show / update / remove` 复制
   `yzrws <service> ...` 子命令；workitem 端复用
   `set-<service>` / `unset-<service>` 模式

> 唯一需要改 adapter 的场景：未来出现非 HTTP 的 MCP server（如 SSE）且
> 某引擎的 `type` 命名与 MCP 规范不一致——届时在 §"协议差异与翻译表"
> 补充一行即可，主体逻辑不变。
