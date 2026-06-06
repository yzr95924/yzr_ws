# 元数据管理设计

## 概述

`metadata.json` 是 workspace 级别的元数据文件，位于 `~/yzr_workspace/metadata.json`。
它记录 workspace 自身的信息、统计摘要和快速访问索引，供 `yzrws` 的各个命令读取。

核心原则：**文件系统是唯一真相源，`metadata.json` 只存储不可派生的信息和性能敏感的索引缓存**。
任何可以从文件系统直接推导的数据，都不应重复存储在 `metadata.json` 中。

## 场景分析

### 场景一：workspace 信息展示

**触发条件**：用户执行 `yzrws info` 或 `yzrws status` 查看工作区状态。

**期望行为**：快速展示工作区名称、创建时间、工作项统计等信息，无需扫描全部目录。

**困难与挑战**：

- 如果每次都扫描全部工作项目录获取统计信息，工作项数量多时会有明显延迟
- 需要在准确性和性能之间找到平衡

### 场景二：最近工作项快速访问

**触发条件**：用户想快速切换回最近活跃的工作项，如 `yzrws resume`（无参数恢复最近的工作项）。

**期望行为**：直接读取最近活跃工作项信息，无需列出全部工作项让用户选择。

**困难与挑战**：

- "最近活跃"需要在工作项操作时增量更新，否则需要扫描全部 session.json 的时间戳
- 需要限制缓存数量（如 top 5），避免文件膨胀

### 场景三：schema 版本迁移

**触发条件**：`yzrws` 升级后，`metadata.json` 的 schema 版本与工具期望版本不一致。

**期望行为**：检测到版本差异，提示用户运行迁移命令（或自动迁移）。

**困难与挑战**：

- 需要预留版本字段，并在每次读取时检查
- 版本兼容策略需要明确：低版本警告、高版本报错

### 场景四：工作项创建 / 删除后的同步

**触发条件**：用户执行 `yzrws create workitem` 或 `yzrws delete workitem`。

**期望行为**：自动更新 `metadata.json` 的统计信息，保持与实际状态一致。

**困难与挑战**：

- 如果用户手动操作目录（`mkdir` / `rm`），`metadata.json` 会与实际不一致
- 需要提供 `yzrws sync` 或 `yzrws doctor` 命令修复漂移（暂不实现）

### 场景汇总

| 场景 | 触发条件 | 核心挑战 | 涉及的设计章节 |
| --- | --- | --- | --- |
| 信息展示 | `yzrws info` | 性能 vs 准确性 | §维护策略 |
| 快速访问 | `yzrws resume` | 增量更新最近活跃 | §recent_workitems 字段 |
| 版本迁移 | schema 版本差异 | 兼容策略 | §版本兼容 |
| 创建 / 删除同步 | workitem 操作 | 手动操作导致的漂移 | §维护策略 |

## 方案选择

### 备选方案

#### 方案 A：文件系统为唯一真相源

`metadata.json` 只存储不可派生信息（版本、创建时间），所有统计信息从文件系统实时扫描。

- 收益：不存在不一致问题；手动操作目录无需额外同步
- 代价：`yzrws list` / `yzrws info` 每次都需扫描全部工作项，工作项多时有延迟

#### 方案 B：完整注册表

`metadata.json` 维护完整的工作项注册表，所有工作项信息都集中存储。

- 收益：读取性能 O(1)；可以追踪已删除工作项的历史
- 代价：手动操作目录会导致注册表与实际不一致；需要 `sync` / `doctor` 命令修复；
  文件膨胀

#### 方案 C：不处理（基线）

不维护 `metadata.json`，所有信息从文件系统实时获取。

- 适用于：工作项数量极少（< 5 个）、不在意性能的早期阶段

### 对比矩阵

| 维度 | 方案 A | 方案 B | 不处理 |
| --- | --- | --- | --- |
| 一致性 | 强一致 | 可能漂移 | 强一致 |
| 读取性能 | O(n) 扫描 | O(1) | O(n) 扫描 |
| 手动操作兼容 | 自动适配 | 需要 sync | 自动适配 |
| 历史追踪 | 不支持 | 支持 | 不支持 |
| 实现复杂度 | 低 | 高 | 最低 |

### 推荐方案

推荐方案 A（文件系统为唯一真相源），并在 `metadata.json` 中维护轻量的统计缓存。

理由：

1. 工作项数量在个人使用场景下通常不超过 50 个，全量扫描的延迟可接受（< 100ms）
2. 强一致性是刚需——用户手动删除目录后，`yzrws list` 应立即反映，而非等待 `sync`
3. 统计缓存（`stats` 字段）在 `create` / `delete` 时增量更新，兼顾性能
4. "最近活跃工作项"是性能敏感的场景，需要 `recent_workitems` 缓存（top 5）

### 否决理由

- **方案 B**：完整注册表引入强一致性问题，手动操作目录后必须 `sync`，
  违背"文件系统是唯一真相源"的原则；实现复杂度高，当前阶段不值得
- **不处理**：完全无缓存会导致 `yzrws status` 等命令每次都全量扫描，
  虽然性能可接受，但缺少 `recent_workitems` 会让 `yzrws resume` 变慢

## 三类数据区分

元数据按"是否可派生"和"派生成本"分为三类，`metadata.json` 只存储前两类：

### 第一类：不可派生（必须显式存储）

这些信息无法从文件系统推导，丢失后无法恢复：

- **workspace 名称 / 描述**：用户自定义的标识信息
- **创建时间**：workspace 何时初始化
- **schema 版本**：用于未来迁移

### 第二类：可派生但成本高（索引缓存）

理论上可以扫描文件系统得到，但每次扫描代价较大，适合缓存到 `metadata.json`
并在变更时增量更新：

- **工作项统计**（总数、活跃数、已完成数）：`yzrws status` 频繁读取
- **知识库文件数**：`yzrws info` 展示用
- **最近活跃工作项**（top 5）：`yzrws resume` 快速访问用

### 第三类：完全可派生（不需要追踪）

随时可以从文件系统得到，存储一份反而容易不一致：

- **工作项目录列表**：`ls ~/yzr_workspace/` 即可
- **每个工作项的详细元数据**：读取 `<workitem>/workitem.json`
- **知识库文件列表和内容**：`ls ~/yzr_workspace/knowledge/` + 读取文件
- **配置文件内容**：读取 `.config/` 下的文件

> `metadata.json` 只存储第一类和第二类数据。第三类数据由各命令在运行时从文件系统获取。

## 完整 Schema

```jsonc
// ~/yzr_workspace/metadata.json
{
  // ── 第一类：不可派生 ──
  "version": "1.0",                              // schema 版本，用于迁移检测
  "name": "我的工作台",                            // 用户自定义名称（可选，默认空）
  "description": "",                              // 工作区描述（可选，默认空）
  "created_at": "2026-06-06T10:00:00+08:00",     // workspace 创建时间
  "updated_at": "2026-06-06T14:00:00+08:00",     // 最后更新时间（任何字段变更时刷新）

  // ── 第二类：索引缓存（增量更新）──
  "stats": {
    "workitem_count": 5,                          // 工作项总数
    "active_workitem_count": 3,                   // status=active 的工作项数
    "completed_workitem_count": 2,                // status=completed 的工作项数
    "knowledge_file_count": 8                     // knowledge/ 下的文件数
  },

  "recent_workitems": [
    // 最近活跃的工作项（top 5，按 last_active_at 降序）
    {
      "name": "api-refactor",
      "status": "active",
      "last_active_at": "2026-06-06T14:00:00+08:00"
    },
    {
      "name": "doc-restructure",
      "status": "active",
      "last_active_at": "2026-06-05T18:00:00+08:00"
    }
    // ... 最多 5 条
  ]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `version` | string | ✓ | schema 版本，当前固定为 `"1.0"` |
| `name` | string | ✗ | 用户自定义的 workspace 名称 |
| `description` | string | ✗ | 工作区描述 |
| `created_at` | string (ISO 8601) | ✓ | workspace 创建时间 |
| `updated_at` | string (ISO 8601) | ✓ | 最后更新时间 |
| `stats` | object | ✓ | 统计信息缓存 |
| `stats.workitem_count` | number | ✓ | 工作项总数 |
| `stats.active_workitem_count` | number | ✓ | 活跃工作项数 |
| `stats.completed_workitem_count` | number | ✓ | 已完成工作项数 |
| `stats.knowledge_file_count` | number | ✓ | 知识库文件数 |
| `recent_workitems` | array | ✓ | 最近活跃工作项（最多 5 条） |
| `recent_workitems[].name` | string | ✓ | 工作项名称 |
| `recent_workitems[].status` | string | ✓ | 工作项状态 |
| `recent_workitems[].last_active_at` | string (ISO 8601) | ✓ | 最后活跃时间 |

## 维护策略

`metadata.json` 的字段按"何时更新"分为两类：

### 初始化时写入（仅一次）

- `version`：固定为 `"1.0"`
- `created_at`：当前时间
- `updated_at`：当前时间（初始值等于 `created_at`）
- `name` / `description`：空字符串（用户可通过 `yzrws config set` 修改）
- `stats`：全零
- `recent_workitems`：空数组

### 增量更新（其他命令触发）

| 触发命令 | 更新的字段 | 更新逻辑 |
| --- | --- | --- |
| `yzrws create workitem` | `stats.workitem_count++`, `stats.active_workitem_count++`, `recent_workitems`（追加）, `updated_at` | 新工作项加入统计和最近活跃列表 |
| `yzrws delete workitem` | `stats.workitem_count--`, `stats.active_workitem_count--`（如适用）, `recent_workitems`（移除）, `updated_at` | 从统计和最近活跃列表中移除 |
| `yzrws start <workitem>` | `recent_workitems`（更新或追加）, `updated_at` | 工作项变为活跃，更新 `last_active_at` |
| `yzrws archive <workitem>` | `stats.active_workitem_count--`, `stats.completed_workitem_count++`, `updated_at` | 状态变更时更新统计 |
| 知识库文件增删 | `stats.knowledge_file_count`, `updated_at` | 扫描 `knowledge/` 目录重新计数 |

### 全量重建（修复漂移）

当用户手动操作目录导致 `metadata.json` 与实际不一致时，
提供 `yzrws sync` 命令全量重建（暂不实现）：

```text
yzrws sync
  │
  ├── 扫描 ~/yzr_workspace/*/workitem.json
  │     └── 重新计算 stats.workitem_count / active / completed
  │
  ├── 扫描 ~/yzr_workspace/knowledge/
  │     └── 重新计算 stats.knowledge_file_count
  │
  ├── 从全部 workitem.json 的 updated_at 排序
  │     └── 重建 recent_workitems（top 5）
  │
  └── 写入 metadata.json（保留 version / name / description / created_at）
```

## 版本兼容

`metadata.json` 的 `version` 字段用于检测 schema 版本是否与当前工具兼容：

| 情况 | 处理策略 |
| --- | --- |
| `version == "1.0"` | 正常读写 |
| `version < "1.0"` | 输出警告，建议运行 `yzrws migrate`（暂不实现） |
| `version > "1.0"` | 输出错误，提示升级 `yzrws` 工具 |

> 当前只有 `"1.0"` 版本，暂无迁移逻辑。未来新增字段时，保持向后兼容（新字段可选），
> 仅在破坏性变更时升级 `version`。

## 不应放入 metadata.json 的数据

以下数据**不属于** workspace 级别的元数据，应放在其他位置：

| 数据 | 应放在 | 理由 |
| --- | --- | --- |
| 默认引擎 / 模型 | `~/.config/yzrws/config.json` | 用户级全局配置，跨 workspace 共享 |
| Provider 信息 | `<workspace>/.config/provider.json` 或 `~/.config/yzrws/provider.json` | 认证信息独立管理，详见 [provider_design.md](./provider_design.md) |
| 工作项详细元数据 | `<workitem>/workitem.json` | 工作项自治，不集中管理 |
| Session 信息 | `<workitem>/session.json` | 工作项级别的会话状态 |
| 知识库文件内容 | `knowledge/*.md` 本身 | 文件即数据，不二次索引 |
| 配置文件内容 | `.config/` 下的文件 | 文件即配置，不重复存储 |

## 与其他文档的关系

- [`workspace_init_design.md`](./workspace_init_design.md)：`yzrws init` 写入 `metadata.json` 的初始值
- [`command_design.md`](./command_design.md)：各命令对 `metadata.json` 的读写操作
- [`session_design.md`](./session_design.md)：工作项级别的 `session.json`，与 workspace 级别的 `metadata.json` 是不同层次
- [`multi_agent_design.md`](./multi_agent_design.md)：引擎配置存储在 `<workitem>/setting.json`，不在 `metadata.json` 中
- [`provider_design.md`](./provider_design.md)：Provider 配置独立管理，不在 `metadata.json` 中
