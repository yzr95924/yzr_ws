# 环境配置设计

## 概述

`yzrws` 仓库的 lint 流程涉及多种语言的工具链（Node.js / Python），因此需要一套统一的环境配置与检查机制。
核心设计原则：

- **单一入口**：`setup.sh` 负责全部环境配置，`lint.sh` 负责全部 lint 检查
- **渐进式检查**：先系统级依赖 → 再虚拟环境 → 再项目级依赖，层层递进
- **可自动也可手动**：`--auto` 模式自动安装可安装的依赖，否则只打印安装方法

## 脚本总览

```text
scripts/
├── setup.sh               # 环境配置统一入口
├── lint.sh                # lint 检查统一入口
└── python/
    ├── lint_md.py         # Markdown lint（markdownlint-cli2 + CJK 空格检查）
    └── lint_py.py         # Python lint（ruff format + ruff check）
```

## 依赖清单

### 系统级依赖（需用户手动安装）

| 依赖 | 用途 | 安装方式 |
| --- | --- | --- |
| Node.js / npm | 运行 markdownlint-cli2 | `brew install node` / `apt install nodejs npm` / nvm |
| Python 3 | 运行 lint 脚本本身 | `brew install python` / `apt install python3` / pyenv |

> 系统级依赖无法由 `setup.sh` 自动安装，仅打印安装方法。

### 项目级依赖（可由 setup.sh 自动安装）

| 依赖 | 安装位置 | 用途 | 自动安装方式 |
| --- | --- | --- | --- |
| markdownlint-cli2 | `node_modules/`（项目级） | Markdown 标准规则检查 | `npm install --save-dev` |
| ruff | `.venv/`（Python venv） | Python 格式化 + lint | `.venv/bin/pip install` |

### 配置文件

| 文件 | 用途 |
| --- | --- |
| `.markdownlint.jsonc` | markdownlint 规则配置（行宽 120，代码块 / 表格除外） |
| `.gitignore` | 排除 `node_modules/`、`.venv/`、`package-lock.json` 等 |

## 环境配置流程（setup.sh）

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

### setup.sh 用法

```sh
# 仅检查，缺失时打印安装方法
./scripts/setup.sh

# 检查 + 自动安装可安装的依赖
./scripts/setup.sh --auto
```

## Lint 检查流程（lint.sh）

`lint.sh` 依次调用两个 Python 脚本：

```text
lint.sh
  ├── python/lint_md.py
  │     ├── markdownlint-cli2    # 标准 Markdown 规则（行宽 120 等）
  │     └── CJK 空格检查         # 中英文 / 中文数字交界处空格（内置）
  └── python/lint_py.py
        ├── ruff format --check  # 代码格式检查
        └── ruff check           # lint 规则检查
```

### 文件收集

两个 Python 脚本都自动扫描仓库内对应后缀的文件，排除以下目录：

- `.git/`
- `node_modules/`
- `__pycache__/`（仅 Python）
- `.venv/`（仅 Python）

### lint.sh 用法

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

## 典型使用流程

```sh
# 1. 首次克隆仓库后
git clone git@github.com:yzr95924/yzr_ws.git
cd yzr_ws
./scripts/setup.sh --auto     # 一键配置环境

# 2. 日常开发中
./scripts/lint.sh              # 提交前检查
./scripts/lint.sh fix          # 自动修复格式问题
```
