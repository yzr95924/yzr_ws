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

- Python 代码全部放在 `src/` 下：主包 `src/yzrws/`，开发工具（lint 调度器）
  `src/devtools/`；`scripts/` 仅保留 shell 脚本。
  **Why:** 语言分层清晰；`src/` 是 Python 社区惯用的产品代码布局；让 `scripts/`
  与 shell 语义对齐。
  **How to apply:** 新增 Python 模块时放到 `src/yzrws/` 对应子包；新增 Python
  开发工具（lint 钩子 / 迁移脚本等）放到 `src/devtools/`。

- 项目自定义 skill 不随仓库分发，而是以"第三方工具"模式管理——由 Code Agent
  通过其自身的 skill 安装 / 发现机制加载，与本仓库解耦。
  **Why:** skill 的迭代节奏与 `yzrws` 工具本身相互独立；维护者可以单独
  更新 / 替换 skill，而不必把 `./skills/` 子目录或 `.claude/skills/`
  软链接之类的胶水状态纳入本仓库的版本控制。
  **How to apply:** 仓库内不再存在 `skills/` 目录或对应子模块；
  文档 / 注释里不要再用 `@./skills/<name>/SKILL.md` 形式内联引用 skill
  实现（路径已不存在），需要提示 agent 使用某个 skill 时直接写 skill
  名即可。

### feedback

- 脚本实现尽量功能归一，避免相同功能产生多个脚本。
  **Why:** 减少维护成本，降低用户认知负担；统一入口便于使用和理解。
  **How to apply:** 新增脚本前先检查是否有可合并的现有脚本；优先扩展已有脚本的参数和功能，而非创建新脚本。

- 文档分工：`doc/` 中的 Markdown 文档侧重详细的设计细节，`README.md` 侧重重点功能的 demo 描述，保持精简不冗长。
  **Why:** README 是快速上手的入口，应让读者快速了解核心用法；详细设计放在 doc/ 中按需查阅，避免信息过载。
  **How to apply:** 更新 README 时只写关键命令和简要说明，细节链接到 doc/；写 doc/ 文档时可以展开完整的背景、流程和决策。

- 脚本实现必须防御性，预防非法 / 模糊输入（不能"主流程跑通就算完"）。
  **Why:** 补全脚本若建议一条最终会被 argparse 拒绝的路径，比不补更糟——
  用户按 Tab 后执行报错会直接失去对工具链的信任；bash 脚本在
  `set -euo pipefail` 下运行，模糊输入（如 `yzrws start --engine claude-code
  <name>`）会让 `cmd_path` 把 flag value 误计为位置参数，导致 dispatch
  走错分支；类似场景在 `install.sh` / `uninstall.sh` 里也会出现（链接指向
  他处、链接被实体文件覆盖、prefix 为空等）。
  **How to apply:** 实现任何"接受用户输入并 dispatch"的脚本时，主动列出
  4 类错误组合并各自设计处理——
  1. **值被误读为另一种语义**（flag value 当成位置参数、链接被当目录等）：
     用显式 schema（value-taking flag 表、`readlink` 比对、参数类型校验）剥离
  2. **边界深度无结果**（n=3 处 dispatch 返回空、cur 又是空）：仅在合适
     深度（n≥2）兜底；n=0/1 保持空 = "没匹配"，不强行降级
  3. **越级污染**（父级子命令被越级重提、跨子命令互窜）：显式标记每个
     depth 的合法子命令集（case 表 / state machine），越界 `COMPREPLY=()`
  4. **深路径无意义**（n≥4 已超出命令设计）：主函数末尾兜 `*) COMPREPLY=()`
     / 显式 return，防越界误补
  完成后至少写"模拟 dispatch 的测试"覆盖上述 4 类场景——肉眼看代码不算
  验证。具体落地见 `completions/yzrws.bash` 与 `doc/script_design.md`
  "防御性补全原则"一节。

- 沉淀记忆时**优先**写到代码仓的 `./MEMORY.md`（与代码一起 git 流转），
  auto-memory（`~/.claude/projects/.../memory/`）只在确实不适合入库时使用。
  **Why:** 代码仓的 `MEMORY.md` 随 `git clone` 流转，新设备 / 新协作者
  立即可读；auto-memory 留在用户家目录，换机 / 换协作者即丢上下文。
  同一份事实在两处都写易出现"两版本漂移"，靠规则强制归一更稳——优先
  repo 后，auto-memory 只剩真正 agent-side 的"不该入库"条目，职责清晰。
  **How to apply:** 写新记忆前先自问——"这条事实在别人 `git clone` 完仓库
  后是否还有用？"答"是" → 写 `./MEMORY.md`；答"否，仅与当前用户的
  agent 偏好相关"（如个人环境变量、IDE 习惯等不该入仓的内容）→ 才写
  auto-memory，且不要与 `./MEMORY.md` 重复同一事实。

- 实现变动时**必须**同步到对应的设计文档（`doc/*.md`），保证文档与实现一致。
  **Why:** 与代码漂移的设计文档比无文档更糟——读者按文档走会做出与代码
  矛盾的决定。`doc/` 下的设计文档被定位为"按需查阅的设计依据"，一旦
  与实现脱节，违反"防御性补全"等已成文的规则时也无法从文档找到出处。
  **How to apply:** 改实现后，自查是否有对应的设计文档——以下映射表
  是高频对应关系，新 session 应**主动**校验：
  - `scripts/*.sh` ↔ `doc/script_design.md`（每个脚本对应一节）
  - `completions/*` ↔ `doc/script_design.md` "防御性补全原则"小节
  - `src/yzrws/commands/<name>.py` ↔ `doc/command_design.md` /
    `doc/<name>_design.md`（如 `provider.py` ↔ `provider_design.md`）
  - 新增 / 删除 / 重命名子命令 / flag ↔ 同步更新 `README.md` 命令速查
  若有现成表格 / 流程图 / 错误组合清单，先看是否能"在原结构里加一行 /
  改一个数"——避免另开新节，破坏"单点修改"的可追溯性。

### reference

<!-- 暂无记录 -->

### user

<!-- 暂无记录 -->
