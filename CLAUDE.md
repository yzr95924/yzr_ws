# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# yzr_ws - 源码仓库

@./MEMORY.md

本仓库是 workspace 管理器的源码（scaffolding 形态），并非传统的可编译/可测试代码项目。详细设计参考 [README.md](./README.md)。

## 项目定位

`yzrws` 是一个轻量的 Code Agent 包装工具，用于管理日常工作：
- 每个任务作为 `workspace/` 下一个"工作项"目录，配有一个可恢复的 Code Agent Session
- 不绑定特定 Code Agent；当前主要考虑 Claude Code 与 OpenCode（兼容性以 CLAUDE.md 为准）
- 知识库设计参考 [karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## 目录语义

| 目录 | 用途 |
| --- | --- |
| `local_wiki/` | 知识库 `*.md`（懒加载；按需 `ls`/`grep`/`Read`） |
| `raw/` | 原始语料，原则上不纳入 git |
| `schema/` | 不同类 wiki 知识的总结模板 |
| `scripts/` | 常用 helper 脚本 |
| `skills/` | 自定义 skill（Claude Code skill） |
| `workspace/<work-item>/` | 单个工作项；含 `.workitem.json`、`.session_id`、本地的 `CLAUDE.md`、`setting.json` |

> 当前各子目录除 `.gitkeep` 外为空，结构处于"骨架"阶段；具体实现按需填入。

## 知识库 / Memory 管理原则

- `./local_wiki`：知识库 markdown 文件。**按需查询**（`ls` / `grep` / `Read`），**不要全量加载**到上下文。
- `./MEMORY.md`：长期记忆。本文顶部 `@./MEMORY.md` 已自动注入到上下文，**无需手动 `Read`**。内容为空时（当前状态）即代表尚无跨工作项长期记忆。
- 写入记忆时遵循项目的 `user / feedback / project / reference` 类型划分（参见 [README.md](./README.md) 中对 karpathy/llm-wiki 设计思路的引用）。

## 工作约定

- 仓库无构建/测试/单测命令——这是工作项容器，不是可执行工程。不要伪造 `pytest` / `make` 等不存在的工具链。
- 修改 `MEMORY.md` / `CLAUDE.md` 等顶层文档前，先与用户确认意图（这些是给所有未来 session 看的共享上下文）。
- 跨工作项的"为什么"应写入 `MEMORY.md`（project 类型）；工作项内的"为什么"应写入该工作项目录下的 `CLAUDE.md`。

## 代码风格

- 主语言：Python 3（推荐 3.11+）。特殊场景（胶水/系统脚本/CI 步骤）可用 Bash。
- 类型注解：公共函数必须有类型签名；模块内部可适度省略。
- 格式化和 lint：统一使用 [ruff](https://docs.astral.sh/ruff/)——`ruff format` 负责格式，`ruff check` 负责 lint（默认规则集即可），不要引入 black/flake8/isort 等替代工具。
- Markdown 格式化和 lint：统一使用 [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)（`markdownlint-cli2` + 默认 `.markdownlint.jsonc` 规则集），范围覆盖仓库内**全部** `*.md` 文件（含 `README.md` / `CLAUDE.md` / `MEMORY.md` / `local_wiki/` / 各 `workspace/<work-item>/`）；不要引入 prettier / remark-lint 等替代工具。
- 注释与文档字符串：**中文**（与 `README.md`/`CLAUDE.md` 保持一致）；只在 WHY 不显然时写注释，不要复述 WHAT。
- 中英文 / 中文数字混排时，**必须**在交界处补一个半角空格（`U+0020`），例如 `使用 ruff 进行 format` 而非 `使用ruff进行format`、`共 12 个文件` 而非 `共12个文件`。代码标识符内部的连接（`ruff_check`、`workitem.json`）不受此约束。
- Bash 脚本开头统一加 `set -euo pipefail`，复杂逻辑使用 `shellcheck` 兜底检查。
- 当前各子目录仍为骨架（仅 `.gitkeep`），上述规范为"目标态"——新增 Python/Bash 文件时直接遵循。