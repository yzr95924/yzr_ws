# yzr_workspace

> 基于 Code Agent 的轻量级工作项管理器 —— 让每个任务都可恢复、可隔离、可沉淀

`yzrw` 是一个轻量的 Code Agent 包装工具, 把日常工作拆解为"工作项"来管理. 每个工作项是一个独立目录, 绑定一个可恢复的 Code Agent Session, 并配套可沉淀的本地知识库与跨工作项的长期记忆.

## 设计思想

**工作项 (Work Item)**
- 每个任务对应 `workspace/<work-item>/` 下一个独立目录
- 每个工作项绑定一个可恢复的 Code Agent Session, 支持断点续传
- 工作项之间互不污染, 可并发推进多个任务

**Agent 无关**
- 不绑定特定 Code Agent; 当前主要适配 Claude Code 与 OpenCode
- 以 `CLAUDE.md` 作为项目规则入口, 兼容主流 Agent

**知识沉淀**
- 本地知识库 (`local_wiki/*.md`): 按需懒加载, 避免上下文过载
- 长期记忆 (`MEMORY.md`): 跨工作项持久化关键决策与偏好
- 远程 Wiki: 可对接个人 Outline Wiki，实现远端 Outline Wiki 的读取、查询、编辑
- 原始语料 (`raw/`): 存放未整理的素材, 原则上不纳入 git
- 设计思路参考 [karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 目录结构

```
local_wiki/             # 知识库 *.md, 按需懒加载
raw/                    # 原始语料, 原则上不纳入 git
schema/                 # 不同类 wiki 知识的总结模板
scripts/                # 常用 helper 脚本
skills/                 # 自定义 skill
workspace/              # 工作项根目录
└── <work-item>/        # 单个工作项目录
    ├── .workitem.json  # 元数据 (name / create_at / status)
    ├── .session_id     # 当前 Code Agent session id
    ├── CLAUDE.md       # 本工作项的上下文
    └── setting.json    # per-workitem 模型/服务商 env

MEMORY.md               # 跨工作项长期记忆
CLAUDE.md               # Code Agent 规则
README.md               # 项目说明
```

## 安装
```sh
$> git clone git@github.com:yzr95924/yzr_workspace.git
$> cd yzr_workspace
$> ./scripts/install.sh
# 1. 将 ./bin 添加到 PATH 环境变量
```

## 配置
### 模型配置
- `yzrw` 支持给不同的 workitem 配置不同的模型、服务商；Provider 定义存储在 `~/.config/yzrw/provider.json`
- 交互方式如下：
```sh
$> yzrw model provider add
# 提示依次提示输入：Base URL，Auth token，Model name
```
或者直接编辑`~/.config/yzrw/provider.json`


## 常用命令