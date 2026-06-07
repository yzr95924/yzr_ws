# yzr_ws

> 基于 Code Agent 的轻量级工作项管理器 —— 让每个任务都可恢复、可隔离、可沉淀，最终可以归档到远端 Outline wiki

`yzrws` 是一个轻量的 Code Agent 包装工具，把日常工作拆解为"工作项"来管理。每个工作项是一个独立目录，绑定一个可恢复的 Code Agent Session，并配套可沉淀的工作项本地知识与跨工作项的长期记忆。

## 工作区设计思想

工作区（workspace）默认路径为 `~/yzr_workspace`，工作区目录定义如下：

```text
~/yzr_workspace
├── <work-item>/        # 单个工作项目录
│   ├── raw/            # 原始语料（未整理素材，不纳入 git）
│   ├── local_wiki/     # 工作项本地知识（Markdown 文档）
│   ├── workitem.json   # 元数据（name / create_at / status）
│   ├── session_id      # 当前 Code Agent session id
│   ├── CLAUDE.md       # 本工作项的上下文
│   └── setting.json    # per-workitem 模型 / 服务商 env
├── MEMORY.md           # 跨工作项长期记忆
├── knowledge/          # 全局共享知识库（*.md，按需懒加载）
├── metadata.json       # 工作区元数据
└── .config/            # 工作区级配置文件
```

### 工作项（Work Item）

- 每个工作项对应工作区目录下的一个子目录
- 每个工作项绑定一个可恢复的 Code Agent Session，支持断点续传
- 工作项之间互不污染，可并发推进多个任务

### Agent 无关

- 不绑定特定 Code Agent；当前主要适配 Claude Code 与 OpenCode
- 以 `CLAUDE.md` 作为项目规则入口，兼容主流 Agent

### 知识沉淀

- 工作项本地知识（`local_wiki/*.md`）：每个工作项内的 Markdown 文档，按需懒加载，避免上下文过载
- 全局共享知识库（`~/yzr_workspace/knowledge/*.md`）：跨工作项共享的知识，按需懒加载
- 长期记忆（`MEMORY.md`）：跨工作项持久化关键决策与偏好
- 远程 Wiki：可对接个人 Outline Wiki，实现远端 Outline Wiki 的读取、查询、编辑
- 原始语料（workitem 内的 `raw/`）：存放未整理的素材，原则上不纳入 git
- 设计思路参考 [karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 代码仓工程目录结构

```text
bin/                    # 需暴露到 PATH 的可执行入口
completions/            # shell 命令自动补全脚本
doc/                    # 核心详细设计文档
schema/                 # 不同类 wiki 知识的总结模板
scripts/                # 仅放 shell 安装 / helper 脚本
src/                    # Python 代码：主包 src/yzrws/，开发工具 src/devtools/
MEMORY.md               # 本项目的长期记忆
CLAUDE.md               # Code Agent 规则
README.md               # 项目说明
```

## 安装 & 卸载

### 安装

> TODO：`scripts/install.sh` 尚未实现，当前需手动将 `./bin` 加入 `PATH`。

```sh
git clone git@github.com:yzr95924/yzr_ws.git
cd yzr_ws
# 手动将 ./bin 添加到 PATH 环境变量
```

### 卸载

TODO

## 开发环境配置

本仓库的 lint 流程依赖 Node.js / npm（用于 markdownlint-cli2）和 Python 3（用于 ruff）。

```sh
# 1. 一键配置环境（检查依赖 + 创建 venv + 安装项目级工具）
./scripts/setup.sh --auto

# 2. 运行 lint 检查
./scripts/lint.sh

# 3. 自动修复格式问题
./scripts/lint.sh fix
```

详细设计见 [`doc/setup_design.md`](./doc/setup_design.md)。

## 配置

### 模型配置

- `yzrws` 支持给不同的 workitem 配置不同的模型、服务商；Provider 配置统一存放在
  workspace 下的 `<workspace>/.config/provider.json`（**不**维护用户级副本）
- 交互方式如下：

```sh
$> yzrws model provider add
# 依次提示输入：Provider 名称、Base URL、Auth Key、Model name
```

或者直接编辑 `<workspace>/.config/provider.json`。所有字段也可通过
`--name` / `--base-url` / `--auth-key` / `--model` / `--agent-type`（可多次）参数传入
以便脚本化。`--agent-type` 用于标注该 Provider 的 `base_url` 兼容的 engine
（`claude-code` / `opencode`），缺省时兼容所有已注册 engine；workitem 选中不兼容
的 Provider 时 `yzrws workitem set-model` 会报错。

### 给 workitem 绑定 Provider

```sh
yzrws workitem set-model <name> --provider <name>   # 绑定（兼容性检查）
yzrws workitem unset-model <name>                   # 解除（恢复继承 workspace 默认）
yzrws workitem show <name>                          # 详情 + 回退链解析结果
```

绑定后 `yzrws start <name>` 启动前会按回退链加载 `(base_url, auth_key, model)`，
分别注入到 Claude Code 的 `ANTHROPIC_*` 环境变量或 OpenCode 的 `opencode.json`。

## 常用命令

```sh
# 初始化工作区
yzrws init

# 创建 / 列举 / 打开工作项
yzrws create workitem <name> [--engine <engine>] [--start]
yzrws list
yzrws start <name> [--engine <engine>] [--new]

# 管理 Provider（workspace 级 .config/provider.json）
yzrws model provider add [--name <name> --base-url <url> --auth-key <key> --model <model>] [--agent-type <engine>]... [--set-default] [-y]
yzrws model provider list
yzrws model provider remove <name> [-y]
yzrws model provider set-default <name>

# 给 workitem 绑定 Provider（生效的 model 由 yzrws start 按回退链加载）
yzrws workitem set-model <name> --provider <name>
yzrws workitem unset-model <name>
yzrws workitem show <name>
```

## Shell 补全

`completions/` 下提供了 bash / zsh / fish 三套补全脚本，覆盖所有子命令与 flag，
并能在补全时从 `YZR_WORKSPACE`（默认 `~/yzr_workspace`）下实时读取工作项与
Provider 名称，无需 yzrws 自身暴露额外接口。

```sh
# 一键安装到默认目录（按 $SHELL 自动选择）
./scripts/install-completions.sh

# 或一次性为所有 shell 安装
./scripts/install-completions.sh --shell all

# 卸载
./scripts/install-completions.sh --uninstall
```

安装路径：

| Shell | 目标位置 | 激活方式 |
| --- | --- | --- |
| bash | `~/.local/share/bash-completion/completions/yzrws` | 重启 shell 即可（依赖 bash-completion 2.x） |
| zsh | `~/.zsh/completions/_yzrws` | 需在 `~/.zshrc` 中加入 `fpath=(~/.zsh/completions $fpath)` 与 `autoload -U compinit && compinit` |
| fish | `~/.config/fish/completions/yzrws.fish` | fish 启动时自动加载 |

补全时支持以下动态值：

- `start` / `workitem *` 的工作项名：扫描 `YZR_WORKSPACE` 下的子目录
- `model provider {remove,set-default}` 与 `workitem set-model --provider` 的 Provider
  名：解析 `<workspace>/.config/provider.json` 的 `providers` 键
- `--engine` / `--agent-type` 的 engine 名：与 `src/yzrws/engine/__init__.py`
  静态注册表保持一致（`claude-code` / `opencode`）

## 其他详细设计

具体设计逻辑参考 `./doc` 目录：

- 命令设计：[`./doc/command_design.md`](./doc/command_design.md)
- 元数据管理：[`./doc/metadata_design.md`](./doc/metadata_design.md)
- 多 Agent 引擎：[`./doc/multi_agent_design.md`](./doc/multi_agent_design.md)
- Provider 配置：[`./doc/provider_design.md`](./doc/provider_design.md)
- 工作项创建：[`./doc/workitem_create_design.md`](./doc/workitem_create_design.md)
- workspace 初始化：[`./doc/workspace_init_design.md`](./doc/workspace_init_design.md)
- Session 管理：[`./doc/session_design.md`](./doc/session_design.md)
- 环境配置：[`./doc/setup_design.md`](./doc/setup_design.md)
- Outline Wiki 对接：[`./doc/outline_wiki_design.md`](./doc/outline_wiki_design.md)（骨架）
