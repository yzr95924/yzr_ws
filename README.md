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
scripts/                # 安装 / helper 脚本
skills/                 # 自定义 skill
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

- `yzrws` 支持给不同的 workitem 配置不同的模型、服务商；Provider 定义存储在 `~/.config/yzrws/provider.json`
- 交互方式如下：

```sh
$> yzrws model provider add
# 依次提示输入：Base URL、Auth token、Model name
```

或者直接编辑 `~/.config/yzrws/provider.json`。

## 常用命令

TODO

## 其他详细设计

具体设计逻辑参考 `./doc` 目录：

- 命令设计：[`./doc/command_design.md`](./doc/command_design.md)
- 元数据管理：[`./doc/metadata_design.md`](./doc/metadata_design.md)
- Outline Wiki 对接：[`./doc/outline_wiki_design.md`](./doc/outline_wiki_design.md)
- Session 管理：[`./doc/session_design.md`](./doc/session_design.md)
- 环境配置：[`./doc/setup_design.md`](./doc/setup_design.md)
