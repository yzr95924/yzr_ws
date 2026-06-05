# MEMORY.md — yzrws 工具开发长期记忆

> 本文件记录**开发 `yzrws` 工具本身**相关的跨 session 长期决策（架构选择、API 约定、踩过的坑等）。
>
> 用户日常工作的跨工作项记忆请写到 `~/yzr_workspace/MEMORY.md`（运行时工作区），不要混在这里。

## 使用约定

- 每条记忆按类型分类：
  - `project`：开发决策、版本节奏、未决问题
  - `feedback`：用户对开发流程 / 风格的明确偏好（含成功确认，不只是纠正）
  - `reference`：外部资源指针（设计参考、相关 issue、上游项目）
  - `user`：维护者本人的角色 / 偏好背景
- 条目格式：短句陈述事实或决策，必要时跟一行 **Why:** 与 **How to apply:**（参考 Claude Code auto-memory 规范）。
- 写入前先 grep 现有条目，能更新就不要新增；过期条目直接删除而不是叠加"已废弃"标注。
- 内容简洁——本文件会被 `@./MEMORY.md` 自动注入到每个 session 的上下文。

## 条目

### project

- Python 代码统一放在 `scripts/python/` 子目录，不与 shell 脚本混在 `scripts/` 根目录。
  **Why:** 语言分层清晰，避免脚本目录杂乱；便于后续 Python 代码扩展（如引入 pyproject.toml 管理）。
  **How to apply:** 新增 Python 脚本时放到 `scripts/python/`；如果未来 Python 代码量增大，可升级为独立的 `python/` 目录。

### feedback

- 脚本实现尽量功能归一，避免相同功能产生多个脚本。
  **Why:** 减少维护成本，降低用户认知负担；统一入口便于使用和理解。
  **How to apply:** 新增脚本前先检查是否有可合并的现有脚本；优先扩展已有脚本的参数和功能，而非创建新脚本。

- 文档分工：`doc/` 中的 Markdown 文档侧重详细的设计细节，`README.md` 侧重重点功能的 demo 描述，保持精简不冗长。
  **Why:** README 是快速上手的入口，应让读者快速了解核心用法；详细设计放在 doc/ 中按需查阅，避免信息过载。
  **How to apply:** 更新 README 时只写关键命令和简要说明，细节链接到 doc/；写 doc/ 文档时可以展开完整的背景、流程和决策。

### reference

<!-- 暂无记录 -->

### user

<!-- 暂无记录 -->
