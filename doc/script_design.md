# scripts/ 目录设计

## 概述

`scripts/` 目录集中存放 `yzrws` 仓库的所有 shell 入口脚本，按用途分为三组：

- **开发期工具链**：`setup.sh`（环境配置）、`lint.sh`（格式 + lint 检查）—— 服务于"开发 `yzrws` 工具本身"
- **交付期**：`install.sh` / `uninstall.sh`（把 `yzrws` 装到 / 卸出 `PATH`）—— 服务于"把 `yzrws` 工具交付给用户"
- **补全子层**：`install-completions.sh`（bash / zsh / fish 补全的安装与卸载）—— 补全部署的事实实现者，被 `install.sh` / `uninstall.sh` 复用

> 后续新增的 `.sh` 脚本（如未来可能出现的 `release.sh` / `migrate.sh` 等）
> 也应在本文件补充对应章节，遵循下文"公共约定"和已有脚本的写作风格。
> 命名沿用其他设计文档的 `<topic>_design.md` 格式，但本文件是**所有 shell
> 脚本设计的汇聚点**，不是某单一脚本的设计文档。

### 通用设计原则

- **单一入口**：每个职责一个入口脚本（`setup.sh` / `lint.sh` / `install.sh`），
  内部再 `exec` 子脚本（如 `install.sh` 调 `install-completions.sh`），避免
  同一类操作分散在多个脚本
- **幂等性**：所有脚本均可重复运行；不重复创建链接 / 配置文件，
  未发现目标时静默跳过
- **安全兜底**：卸载类操作不会误删他处同名文件（`uninstall.sh` 通过
  `readlink` 比对目标）
- **可观察**：每个步骤打印状态（"已安装 / 已跳过 / 拒绝覆盖"），失败时给
  出可读的错误信息
- **可测试**：所有写入路径都接受 `--dest-dir` / `--dest-base` / `--prefix`
  等参数，staging 测试可在临时目录完成

## 公共约定

所有 `scripts/*.sh` 共享以下写法，便于读 / 改 / 审：

- **严格模式**：`set -euo pipefail`（任何命令失败 / 未定义变量 / pipe 失败都会中止）
- **头注释 / `--help`**：脚本顶部 8-15 行注释描述用途、用法；`-h | --help` 时
  `sed -n '<起,止>p' "$0"` 打印这段注释
- **`SCRIPT_DIR` / `REPO_ROOT` 锚点**：开头用
  `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` 定位脚本自身，
  再 `REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"` 推出仓库根，**不**假设当前工作目录
- **参数解析**：`while [[ $# -gt 0 ]]; do case "$1" in ... esac done` 显式解析，
  支持 `-h | --help`，未知参数 `exit 2`
- **中文注释**：与 `README.md` / `CLAUDE.md` 保持一致；只在 WHY 不显然时写注释
- **可执行权限**：新脚本需 `chmod +x`，仓库内的 `*.sh` 在 git 中均带执行位

> 仓库暂未引入 `shellcheck`（本机环境不一定安装），但所有 `*.sh` 已按
> `shellcheck` 通过为目标书写——避免 trap / SC2086 / 引号缺失等常见问题。
> 后续若将 `shellcheck` 纳入 `lint.sh`，本文件应同步补一节"shellcheck 适配清单"。

## 脚本总览

```text
scripts/
├── setup.sh                       # 开发期：环境配置统一入口（lint 工具链）
├── lint.sh                        # 开发期：lint 检查统一入口
├── install.sh                     # 交付期：安装 yzrws 主命令到 PATH + 补全
├── uninstall.sh                   # 交付期：卸载 yzrws 主命令 + 补全
└── install-completions.sh         # 补全子层：补全安装 / 卸载（被 install.sh / uninstall.sh 复用）

src/
├── yzrws/                 # 主包
└── devtools/
    ├── lint_md.py         # Markdown lint（markdownlint-cli2 + CJK 空格检查）
    └── lint_py.py         # Python lint（ruff format + ruff check）
```

> `scripts/` 仅放 shell 脚本；Python 全部在 `src/` 下：
> 主包 `src/yzrws/`，开发工具（lint 调度器）`src/devtools/`。

---

## setup.sh — 开发环境配置

`setup.sh` 解决"开发 `yzrws` 工具自身"需要的多语言工具链准备（Node.js / Python
相关）。核心设计原则：

- **单一入口**：`setup.sh` 负责全部环境配置，`lint.sh` 负责全部 lint 检查
- **渐进式检查**：先系统级依赖 → 再虚拟环境 → 再项目级依赖，层层递进
- **可自动也可手动**：`--auto` 模式自动安装可安装的依赖，否则只打印安装方法

### 依赖清单

#### 系统级依赖（需用户手动安装）

| 依赖 | 用途 | 安装方式 |
| --- | --- | --- |
| Node.js / npm | 运行 markdownlint-cli2 | `brew install node` / `apt install nodejs npm` / nvm |
| Python 3 | 运行 lint 脚本本身 | `brew install python` / `apt install python3` / pyenv |

> 系统级依赖无法由 `setup.sh` 自动安装，仅打印安装方法。

#### 项目级依赖（可由 setup.sh 自动安装）

| 依赖 | 安装位置 | 用途 | 自动安装方式 |
| --- | --- | --- | --- |
| markdownlint-cli2 | `node_modules/`（项目级） | Markdown 标准规则检查 | `npm install --save-dev` |
| ruff | `.venv/`（Python venv） | Python 格式化 + lint | `.venv/bin/pip install` |

### 配置文件

| 文件 | 用途 |
| --- | --- |
| `.markdownlint.jsonc` | markdownlint 规则配置（行宽 120，代码块 / 表格除外） |
| `.gitignore` | 排除 `node_modules/`、`.venv/`、`package-lock.json` 等 |

### 配置流程

`setup.sh` 按以下 5 步顺序执行，每一步都有前后依赖关系：

```text
[1/5] Node.js / npm ──────┐
[2/5] Python 3 ───────────┼── 系统级（缺失仅提示，不自动安装）
                          │
[3/5] .venv 虚拟环境 ─────┤── 依赖 Python 3（--auto 可自动创建）
                          │
[4/5] markdownlint-cli2 ──┤── 依赖 npm（--auto 可自动安装）
[5/5] ruff ───────────────┘── 依赖 .venv（--auto 可自动安装）
```

### 依赖查找策略

每个项目级依赖都遵循"项目级优先，全局兜底"的查找策略：

```text
markdownlint-cli2:  node_modules/.bin/markdownlint-cli2  →  全局 PATH
ruff:               .venv/bin/ruff                       →  全局 PATH
```

### 用法

```sh
# 仅检查，缺失时打印安装方法
./scripts/setup.sh

# 检查 + 自动安装可安装的依赖
./scripts/setup.sh --auto
```

---

## lint.sh — 格式与 lint 检查

`lint.sh` 依次调用两个 Python 脚本：

```text
lint.sh
  ├── src/devtools/lint_md.py
  │     ├── markdownlint-cli2    # 标准 Markdown 规则（行宽 120 等）
  │     └── CJK 空格检查         # 中英文 / 中文数字交界处空格（内置）
  └── src/devtools/lint_py.py
        ├── ruff format --check  # 代码格式检查
        └── ruff check           # lint 规则检查
```

### 文件收集

两个 Python 脚本都自动扫描仓库内对应后缀的文件，排除以下目录：

- `.git/`
- `node_modules/`
- `__pycache__/`（仅 Python）
- `.venv/`（仅 Python）

### 用法

```sh
# 检查全部 .md + .py 文件
./scripts/lint.sh

# 自动修复（ruff format + ruff check --fix + markdownlint --fix）
./scripts/lint.sh fix
```

### 自定义检查：CJK 空格

`lint_md.py` 内置了中英文 / 中文数字交界处空格检查（`check_cjk_spacing`），
因为现有 Markdown lint 工具不支持此规则。检查逻辑：

- 跳过 fenced code block、indented code block、HTML 注释
- 跳过行内代码（`` `...` ``）和链接 URL（`[text](url)` 中的 url 部分）
- 检测 CJK 字符与 ASCII 字母 / 数字直接相邻的情况

---

## install.sh / uninstall.sh — yzrws 交付

`setup.sh` / `lint.sh` 处理的是"开发 `yzrws` 工具本身"需要的环境；
而 `install.sh` / `uninstall.sh` 处理的是"把 `yzrws` 这个工具交付给用户"
——把 `bin/yzrws` 暴露到 `PATH`、把 `completions/` 部署到 shell 标准目录。
两者关注点正交，因此单独成节。

### 设计目标

- **零依赖安装**：用户克隆仓库后只需一条命令即可使用，不需要 `pip install` /
  `setup.py` / 打包发布，scaffolding 阶段尤其需要这种"开箱即用"的能力
- **可写回到 PATH**：默认装到 `~/.local/bin`（XDG 标准用户级目录），多数
  发行版默认已在 `PATH` 中，无需 `sudo`
- **git pull 立即生效**：用软链接而非复制，`bin/yzrws` 的改动下一次 `git pull`
  立刻可见
- **可逆**：提供对称的 uninstall，幂等且有安全兜底（不会误删他处同名文件）
- **补全同步**：yzrws 补全只在 shell 启动时加载一次，必须随主命令一起装 / 卸，
  否则会出现"主命令在、但没有补全"或反之的不一致状态

### 安装位置与链接策略

主命令位置由 `--prefix` / `--bin-dir` 控制，默认值：

```text
prefix   = $HOME/.local          # 遵循 XDG Base Directory
bin_dir  = $prefix/bin           # → $HOME/.local/bin
target   = $bin_dir/yzrws        # 软链接，指向 <repo>/bin/yzrws
```

> `~/.local/bin` 是 XDG Base Directory Specification 规定的"user-specific
> executables"标准位置；macOS / 主流 Linux 发行版的 shell rc 通常已包含
> 对它的 `PATH` 注入，无需额外配置。

**用软链接而不是 `cp`** 是经过权衡的：

- `bin/yzrws` 通过 `Path(__file__).resolve().parent` 反推仓库根，所以
  软链接到 `<repo>/bin/yzrws` 实际访问时仍能解析到正确路径
- `git pull` 之后 `bin/yzrws` 的改动对用户立刻可见
- uninstall 只需 `rm` 一个符号链接
- uninstall 还能通过比对 `readlink` 与 `<repo>/bin/yzrws` 来判断"这个链接
  是不是本脚本创建的"，避免误删他处的同名文件

### 补全安装：复用而非重写

`install.sh` 不直接展开补全安装逻辑，而是 `exec` 调用 `install-completions.sh`：

```text
install.sh ──exec──> install-completions.sh --shell <target> --dest-dir <base>
uninstall.sh ──exec──> install-completions.sh --shell <target> --dest-dir <base> --uninstall
```

**Why:**

- `completions/` 下 bash / zsh / fish 三套补全的目标路径（`$fpath` 规则、
  `~/.local/share/bash-completion/completions` 等）由 `install-completions.sh`
  唯一维护
- 当补全路径约定变化时（典型场景：XDG 规则调整），只需改一处
- 用户如果只想管理补全、不动主命令，仍然可以单独调用
  `install-completions.sh`（README 中单独成节"Shell 补全"）

**Why `--dest-base` 透传而不是直接用 `$HOME`：**

- 默认 `DEST_BASE=$HOME`，行为对齐"装到用户主目录"
- 包管理 / 测试场景可传 `--dest-base /tmp/staging` 把补全装到
  `staging/.local/share/bash-completion/completions/yzrws`，
  install 脚本的链接、uninstall 脚本的清理都跟着走，验证流程可全在一棵
  临时目录里跑完

### 参数设计：install / uninstall 严格对称

```text
--prefix <dir>        # 安装根（默认 $HOME/.local），bin 目录 = <prefix>/bin
--bin-dir <dir>       # 直接指定 bin 目录，覆盖 --prefix 推导
--shell <bash|zsh|fish>  # 仅装 / 卸某种 shell 的补全；缺省装 / 卸全部三种
--no-completions      # 仅装 / 卸主命令，跳过补全（与 --shell 互斥）
--dest-base <dir>     # 补全根目录（透传给 install-completions.sh，默认 $HOME）
-h / --help           # 打印脚本头注释
```

**Why 缺省装全部：**

- yzrws 用户通常不止用一种 shell（bash 启动脚本 + 日常 fish / 切到 zsh
  调试都很常见），缺省装全部避免"切到另一种 shell 发现没补全"的尴尬
- 不再做 `$SHELL` 推断——`$SHELL` 反映的是当前 shell 进程，不是用户的
  shell 偏好；推断有歧义，统一装全部更稳
- install 与 uninstall 对称：装了就卸全，卸了就卸全，状态闭环

**Why 对称：**

- 用户心智模型一致："用什么参数装的，就用什么参数卸"
- uninstall 必须能定位 install 留下的所有痕迹，否则会出现"卸了主命令但
  补全还在"或"卸了 bash 补全但 zsh 补全还在"的碎片化状态
- 文档 / README 中 install 与 uninstall 可以共用同一组示例，减小维护成本

**Why `--shell` 不再接受 `all` / `none`：**

- `all` 已成为默认行为，传 `--shell all` 反而冗余
- `none` 等价于 `--no-completions`，两个写法同时存在会逼用户记忆哪个对哪个
- 内部转发到 `install-completions.sh` 时，缺省时显式拼 `--shell all`；
  外部 API 越简单越好

### 幂等性与安全兜底

| 场景 | install.sh 行为 | uninstall.sh 行为 |
| --- | --- | --- |
| 目标位置为空 | 创建链接 + 装补全 | 静默跳过两项 |
| 链接已存在且指向 `<repo>/bin/yzrws` | 跳过链接创建 | 删除链接 |
| 链接指向他处 | **拒绝**（避免覆盖用户的同名命令） | **拒绝删除**（避免误删他处命令） |
| 目标位置是实体文件（非符号链接） | **拒绝** | **拒绝**（只删 install 脚本创建的链接） |
| 部分已安装（链接在 / 补全在） | 跳过已存在的，逐项补齐 | 逐项清理，未发现静默跳过 |

> "拒绝"是兜底而非阻断：用户能清楚地看到冲突点（错误 / 警告信息中
> 包含 `readlink` 实际值），可以自行 `rm` 后重试。

### install.sh 完整流程

```text
[1/2] 解析参数（--prefix / --bin-dir / --shell / --no-completions / --dest-base）
        └─ 缺省值：prefix=$HOME/.local，bin_dir=$prefix/bin，
                    dest_base=$HOME；--shell 缺省时装全部
        └─ 校验 SOURCE_BIN / COMPLETIONS_SCRIPT 存在且可执行
        └─ 校验 --shell 取值（仅 bash/zsh/fish），--no-completions 与 --shell 互斥
[2/2] 创建 <bin_dir>/yzrws → <repo>/bin/yzrws 软链接（幂等 + 安全检查）
[3/3] 若未传 --no-completions：转发 install-completions.sh
        --shell <${SHELL_TARGET:-all}> --dest-dir <dest_base>
[4/4] 打印激活提示（PATH 不含 bin_dir 时给出临时 / 永久启用方案）
```

### uninstall.sh 完整流程

```text
[1/2] 解析参数（同 install.sh）
[2/2] 校验 <bin_dir>/yzrws 是符号链接 且 指向 <repo>/bin/yzrws，匹配则删除
[3/3] 转发 install-completions.sh --shell <target> --dest-dir <dest_base> --uninstall
```

### 与其它脚本的边界

| 脚本 | 职责 | 关系 |
| --- | --- | --- |
| `setup.sh` | 准备**开发** yzrws 需要的工具链（venv、npm、ruff、markdownlint-cli2） | 与 install.sh 无关 |
| `lint.sh` | 对仓库内 `.md` / `.py` 文件做格式 + lint 检查 | 与 install.sh 无关 |
| `install-completions.sh` | 补全安装 / 卸载的**事实实现者** | 被 install.sh / uninstall.sh 转发 |
| `install.sh` | 暴露 `yzrws` 到 PATH + 装补全 | 自身是入口，**不**展开补全逻辑 |
| `uninstall.sh` | 移除 `yzrws` 链接 + 卸补全 | 与 install.sh 参数严格对称 |

> 这套分层让"补全规则变动"只动一个文件，"安装流程变动"只动一对文件。
> 在 scaffolding 阶段随项目成熟而调整时影响面可控。

---

## install-completions.sh — 补全事实实现者

`install-completions.sh` 是补全部署的**唯一**实现者。`install.sh` /
`uninstall.sh` 不直接展开 bash / zsh / fish 的目标路径规则，而是转发到本脚本；
当补全路径约定调整时，只需改这一个文件。

### 职责

- 把 `completions/yzrws.bash` / `_yzrws` / `yzrws.fish` 复制到各 shell 的标准
  补全目录
- 通过 `--uninstall` 把上述文件从对应目录删除
- 重复运行幂等；缺失源文件时明确报错

### 目标路径（与 shell 强相关）

| Shell | 目标位置 | 激活方式 |
| --- | --- | --- |
| bash | `<dest-base>/.local/share/bash-completion/completions/yzrws` | 重启 shell（依赖 bash-completion 2.x） |
| zsh | `<dest-base>/.zsh/completions/_yzrws` | 需在 `~/.zshrc` 中加入 `fpath=(~/.zsh/completions $fpath)` + `autoload -U compinit && compinit` |
| fish | `<dest-base>/.config/fish/completions/yzrws.fish` | fish 启动时自动加载 |

> `<dest-base>` 默认 `$HOME`（与 `install.sh` / `uninstall.sh` 的 `--dest-base` 同义）；
> 包管理 / 测试场景可传入 `/tmp/staging` 等临时根目录。

### 参数

```text
--shell <bash|zsh|fish|all>    # 目标 shell，缺省按 $SHELL 推断
--uninstall                    # 删除模式（与 install 互斥，由 uninstall.sh 调用）
--dest-dir <dir>               # 补全根目录（默认 $HOME）
-h / --help                    # 打印脚本头注释
```

### 与其它脚本的关系

| 调用方 | 调用方式 |
| --- | --- |
| `install.sh` | `install-completions.sh --shell <target> --dest-dir <base>` |
| `uninstall.sh` | `install-completions.sh --shell <target> --dest-dir <base> --uninstall` |
| 用户单独使用 | `install-completions.sh --shell all` 即可（README 中"Shell 补全"一节单独介绍了这种用法） |

### 设计要点

- **每个 shell 一段独立函数**（`install_bash` / `install_zsh` / `install_fish`），
  避免 `case` 中堆叠复杂分支；安装 / 卸载都走同一组函数
- **`--shell all` 时 `|| true`**：逐个 shell 尝试装 / 卸，单一 shell 失败不阻断其它 shell
- **未发现已安装时静默跳过**：与 `uninstall.sh` 主命令的"幂等"语义对齐
- **激活提示独立成节**：脚本尾部根据 `--shell` 打印对应 shell 的 `fpath` /
  `compinit` / `source` 提示，无需用户查文档

> 本节刻意不展开每种 shell 补全的**具体**激活命令——这些已写在脚本的
> "激活提示"段和 README.md "Shell 补全"一节；本文档只描述**为什么**要这样
> 设计（不重复 WHAT）。

### 防御性补全原则

补全脚本的目标是**尽量消除可能的错误命令组合**——让用户按 Tab 永远拿不到
一条最终会被 argparse 拒绝的命令路径。三种 shell 实现路径不同，但目标一致：

| 错误组合 | 触发条件 | bash 处理 | fish 处理 | zsh 处理 |
| --- | --- | --- | --- | --- |
| **flag value 被误计为位置参数** | `yzrws start --engine claude-code <name>` | 主函数构建 `cmd_path` 时跳过 value-taking flag 后的 token（`_yzrws_value_taking_flags`） | flag 标记 `-r` 让 fish 自动不把 value 当位置参数 | `_arguments` 的 `'--engine[desc]:msg:action'` 语法内建处理 |
| **leaf 节点后看不到剩余 flag** | `yzrws model provider add <Tab>`（cur 空、n=3、dispatch 返回空） | 兜底分支：COMPREPLY 空时再调一次 `_yzrws_complete_flags ""` | 每个 flag 独立的 `complete -c` 规则，cur 触发条件一致 | `_arguments` 的 `*` 通配剩余 flag |
| **父级子命令被越级重提** | `yzrws model provider add <Tab>` 后又想补 `model` | cmd_path 仍含 `model`，但当前 case n=3 的位置参数 dispatch 不会去查 n=1 | `not __fish_seen_subcommand_from provider` 排除项 | `case $words[1]` 分发到 leaf，未知 case 落到默认空补全 |
| **跨子命令污染** | `yzrws model --foo <Tab>` 之类的乱写 | `model` 在 cmd_path 位置 0；`--foo` 不在 flag 表，flag 补全返回空 | `model` 规则要求 `not __fish_seen_subcommand_from provider`，否则不触发 | `_yzrws_model` 走 `_arguments -C` 二级 state，未知值默认空 |
| **多参"包含"被 OR 误命中浅层**（fish 特有） | `yzrws model <Tab>` 时 `__fish_seen_subcommand_from model provider` 因 OR 语义只匹配 `model` 就成立，错误地补出 add/list/remove/set-default | n/a | 多参包含条件必须用 `; and` 链式： `__fish_seen_subcommand_from A; and __fish_seen_subcommand_from B` | n/a（zsh 用 `_arguments` 的子状态机，不会有此问题） |
| **同名单词既是顶层又是嵌套子命令**（fish 特有） | `yzrws create workitem <Tab>` 时 `__fish_seen_subcommand_from workitem` 命中（workitem 出现在命令行），导致 `yzrws workitem <subcmd>` 那 5 条规则错误触发，列出 set-model/show 等 | n/a（bash 用位置计数 `n=2` + case `create.workitem` 天然区分） | 顶层 `workitem <subcmd>` 规则必须加 `and not __fish_seen_subcommand_from create` 守卫 | n/a（zsh `_yzrws_create` / `_yzrws_workitem` 是两个独立 state，天然隔离） |

> 三种 shell 都在 `completions/*.sh` 顶部加了对应的"防御性补全原则"注释，
> 与本节表格对齐——这样后续修改任一 shell 补全时，能直接对照此表
> 找出潜在漏洞并修复。

---

## 典型使用流程

```sh
# 1. 首次克隆仓库后
git clone git@github.com:yzr95924/yzr_ws.git
cd yzr_ws
./scripts/setup.sh --auto     # 一键配置环境（开发 yzrws 工具自身）

# 2. 把 yzrws 装到本地 PATH
./scripts/install.sh           # → ~/.local/bin/yzrws + 补全

# 3. 日常开发中
./scripts/lint.sh              # 提交前检查
./scripts/lint.sh fix          # 自动修复格式问题
```
