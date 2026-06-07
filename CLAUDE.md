# yzr_ws — yzrws 工具源码仓库

> This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@./MEMORY.md

本仓库是 `yzrws` 工具的源码（当前为 scaffolding 形态），**不是**工作区本身。工作区默认在 `~/yzr_workspace`（仓库外），其目录约定与设计思想见 [README.md](./README.md)。

## 项目定位

- `yzrws` 是轻量的 Code Agent 包装工具，把日常工作拆解为"工作项"（work item）管理
- 每个工作项 = `~/yzr_workspace/<work-item>/` 下一个目录，含元数据 `workitem.json` /
  `session.json`（会话元数据）、工作项本地的 `CLAUDE.md` / `setting.json`，以及
  `raw/`（原始语料）/ `local_wiki/`（工作项本地知识）子目录
- 不绑定特定 Code Agent；主要适配 Claude Code 与 OpenCode（兼容性以 `CLAUDE.md` 为准）
- 知识库设计参考 [karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 仓库目录（repo 内）

| 目录 | 用途 |
| --- | --- |
| `bin/` | 需暴露到 `PATH` 的可执行入口（`yzrws` 主命令等） |
| `completions/` | shell 命令自动补全脚本 |
| `doc/` | 设计文档；当前已有：[`command_design.md`](./doc/command_design.md)（命令集）/ [`metadata_design.md`](./doc/metadata_design.md) / [`multi_agent_design.md`](./doc/multi_agent_design.md) / [`provider_design.md`](./doc/provider_design.md) / [`script_design.md`](./doc/script_design.md)（所有 `scripts/*.sh` 的设计汇聚点）/ [`session_design.md`](./doc/session_design.md) / [`workitem_create_design.md`](./doc/workitem_create_design.md) / [`workspace_init_design.md`](./doc/workspace_init_design.md)（部分仍为骨架） |
| `schema/` | 不同类 wiki 知识的总结模板 |
| `scripts/` | Shell 安装 / helper 脚本 |
| `src/` | Python 代码；主包 `src/yzrws/`，开发工具（lint 调度器）`src/devtools/` |

> 各目录目前仅含 `.gitkeep` 与少量种子文件，仓库处于"骨架"阶段，按需填入实现。
>
> **不要**在 repo 内创建 `workspace/` / `local_wiki/` / `knowledge/` / `raw/` 子目录——它们都是运行时工作区（`~/yzr_workspace`）下的概念，不属于本仓库结构。
>
> 工作区根目录下还有 `knowledge/`（全局共享知识库，与工作项内的 `local_wiki/` 区分）、
> `metadata.json`（工作区元数据）、`.config/`（工作区级配置），详见 [README.md](./README.md) 的工作区目录树。

## 工作约定

- 仓库目前无构建 / 测试 / 单测命令——这是工具源码 + scaffolding，不是可执行工程。
  不要伪造 `pytest` / `make` 等不存在的工具链；之后引入时先更新本文件再使用。
- 修改 `MEMORY.md` / `CLAUDE.md` / `README.md` 等顶层文档前，先与用户确认意图（这些是给所有未来 session 看的共享上下文）。
- 长期记忆分层：
  - **本仓库的 `./MEMORY.md`**：只记录"开发 `yzrws` 工具本身"相关的长期决策（架构选择、API 约定等）
  - **`~/yzr_workspace/MEMORY.md`**：用户日常工作的跨工作项长期记忆，与本仓库无关
  - **工作项内的 `CLAUDE.md`**：该工作项专属的"为什么"
- 全局知识库（`~/yzr_workspace/knowledge/`）与工作项本地知识（`local_wiki/`）均按需懒加载（`ls` / `grep` / `Read`），**不要全量加载**到上下文。
- 模型 / 服务商（Provider）配置统一存放在 workspace 下的 `<workspace>/.config/provider.json`，
  通过 `yzrws model provider add` 交互添加（详见 [README.md](./README.md)）。
  没有用户级副本——所有 Provider 与 workspace 同生命周期。

## 代码风格

- Lint 统一入口：`./scripts/lint.sh`（检查全部 `.md` + `.py` 文件），
  自动修复用 `./scripts/lint.sh fix`。依赖检查用 `./scripts/setup.sh --auto`。
- 主语言：Python 3（推荐 3.11+）。特殊场景（胶水 / 系统脚本 / CI 步骤）可用 Bash。
- 类型注解：公共函数必须有类型签名；模块内部可适度省略。
- 格式化和 lint：统一使用 [ruff](https://docs.astral.sh/ruff/)——`ruff format` 负责格式，
  `ruff check` 负责 lint（默认规则集即可），不要引入 black / flake8 / isort 等替代工具。
  由 `./scripts/lint.sh` 统一调度。
- Markdown 格式化和 lint：统一使用 [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)
  （默认 `.markdownlint.jsonc` 规则集），范围覆盖仓库内**全部** `*.md` 文件
  （含 `README.md` / `CLAUDE.md` / `MEMORY.md` / `doc/` 等）；不要引入 prettier / remark-lint 等替代工具。
  由 `./scripts/lint.sh` 统一调度。
- 注释与文档字符串：**中文**（与 `README.md` / `CLAUDE.md` 保持一致）；只在 WHY 不显然时写注释，不要复述 WHAT。
- 中英文 / 中文与数字混排时，**必须**在交界处补一个半角空格（`U+0020`），例如 `使用 ruff 进行 format`
  而非 `使用ruff进行format`、`共 12 个文件` 而非 `共12个文件`。
  代码标识符内部的连接（`ruff_check`、`workitem.json`）不受此约束。
- Markdown 单行行宽不超过 120 字符（代码块与表格行除外）。
- Bash 脚本开头统一加 `set -euo pipefail`，复杂逻辑使用 `shellcheck` 兜底检查。

## Skills

项目自定义 skill 不随仓库分发，以"第三方工具"模式由 Code Agent 通过其自身的
skill 加载机制提供；仓库内不再保留 `./skills/` 目录或对应子模块。按需提示
agent 调用 skill 时直接使用 skill 名即可，不要再用
`@./skills/<name>/SKILL.md` 形式内联引用（路径已不存在）。

例如 `design-doc-edit`：当用户要求撰写 / 补充设计文档、分析设计方案、对比技术方案时，
按此 skill 的流程执行；产出物写入 `doc/` 目录，文件名采用 `<topic>_design.md` 格式。
