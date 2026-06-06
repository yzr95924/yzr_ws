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

- 命令格式
  - `yzrws create workitem <workitem_name>`
- 命令具体说明

1. 创建一个 workitem，名字用 `workitem_name`；如果已存在，回显当前 workitem 已存在
2. 若 workitem 不存在，则进入创建流程；在 workspace 目录下创建对应的同名子目录

## 列举 workitem

- 命令格式
  - `yzrws list`
- 命令具体说明

1. 列举当前已存在的 workitem

## 导入 workitem

- 命令格式
  - `yzrws import <workitem_name>`
