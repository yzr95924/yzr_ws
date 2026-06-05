# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# yzr_ws — yzrws 工具源码仓库

@./MEMORY.md

本仓库是 `yzrws` 工具的源码（当前为 scaffolding 形态），**不是**工作区本身。工作区默认在 `~/yzr_workspace`（仓库外），其目录约定与设计思想见 [README.md](./README.md)。

## 项目定位

- `yzrws` 是轻量的 Code Agent 包装工具，把日常工作拆解为"工作项"（work item）管理
- 每个工作项 = `~/yzr_workspace/<work-item>/` 下一个目录，含元数据 `workitem.json` / `session_id`、工作项本地的 `CLAUDE.md` / `setting.json`，以及 `raw/` / `local_wiki/` 子目录
- 不绑定特定 Code Agent；主要适配 Claude Code 与 OpenCode（兼容性以 `CLAUDE.md` 为准）
- 知识库设计参考 [karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 仓库目录（repo 内）

| 目录 | 用途 |
| --- | --- |
| `bin/` | 需暴露到 `PATH` 的可执行入口（`yzrws` 主命令等） |
| `completions/` | shell 命令自动补全脚本 |
| `doc/` | 设计文档；命令集草案见 [`doc/command_design.md`](./doc/command_design.md) |
| `schema/` | 不同类 wiki 知识的总结模板 |
| `scripts/` | 安装 / helper 脚本（README 中 `./scripts/install.sh` 由此加载） |
| `skills/` | 自定义 skill |

> 各目录目前仅含 `.gitkeep` 与少量种子文件，仓库处于"骨架"阶段，按需填入实现。
>
> **不要**在 repo 内创建 `workspace/` / `local_wiki/` / `knowledge/` / `raw/` 子目录——它们都是运行时工作区（`~/yzr_workspace`）下的概念，不属于本仓库结构。

## 工作约定

- 仓库目前无构建 / 测试 / 单测命令——这是工具源码 + scaffolding，不是可执行工程。不要伪造 `pytest` / `make` 等不存在的工具链；之后引入时先更新本文件再使用。
- 修改 `MEMORY.md` / `CLAUDE.md` / `README.md` 等顶层文档前，先与用户确认意图（这些是给所有未来 session 看的共享上下文）。
- 长期记忆分层：
  - **本仓库的 `./MEMORY.md`**：只记录"开发 `yzrws` 工具本身"相关的长期决策（架构选择、API 约定等）
  - **`~/yzr_workspace/MEMORY.md`**：用户日常工作的跨工作项长期记忆，与本仓库无关
  - **工作项内的 `CLAUDE.md`**：该工作项专属的"为什么"
- 知识库 / 原始语料按需懒加载（`ls` / `grep` / `Read`），**不要全量加载**到上下文。
- 模型 / 服务商配置位于 `~/.config/yzrws/provider.json`，通过 `yzrws model provider add` 交互添加（详见 README）。

## 代码风格

- 主语言：Python 3（推荐 3.11+）。特殊场景（胶水 / 系统脚本 / CI 步骤）可用 Bash。
- 类型注解：公共函数必须有类型签名；模块内部可适度省略。
- 格式化和 lint：统一使用 [ruff](https://docs.astral.sh/ruff/)——`ruff format` 负责格式，`ruff check` 负责 lint（默认规则集即可），不要引入 black / flake8 / isort 等替代工具。
- Markdown 格式化和 lint：统一使用 [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)（默认 `.markdownlint.jsonc` 规则集），范围覆盖仓库内**全部** `*.md` 文件（含 `README.md` / `CLAUDE.md` / `MEMORY.md` / `doc/` 等）；不要引入 prettier / remark-lint 等替代工具。
- 注释与文档字符串：**中文**（与 `README.md` / `CLAUDE.md` 保持一致）；只在 WHY 不显然时写注释，不要复述 WHAT。
- 中英文 / 中文与数字混排时，**必须**在交界处补一个半角空格（`U+0020`），例如 `使用 ruff 进行 format` 而非 `使用ruff进行format`、`共 12 个文件` 而非 `共12个文件`。代码标识符内部的连接（`ruff_check`、`workitem.json`）不受此约束。
- Bash 脚本开头统一加 `set -euo pipefail`，复杂逻辑使用 `shellcheck` 兜底检查。
