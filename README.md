# yzr_workspace
基于Code Agent管理日常工作项

## 设计思想
- `yzrw`是一个轻量的Code Agent包装工具，用于管理日常的工作
    - 每个任务作为一个“工作项”目录，配有一个可恢复的Code Agent Session

- 具备知识库沉淀知识的能力
1. 可以对接个人Outline Wiki上远端的知识；
2. 一方面可以将短期知识缓存在本地，以*.md的形式进行持久化，懒加载；
3. 具备跨工作项的长期记忆；
4. 知识库的设计逻辑参考[karpathy/llm-wiki.md](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

- 本项目不绑定特定的Code Agent，当前主要考虑ClaudeCode和OpenCode（从兼容性角度考虑，使用CLAUDE.md）

## 工程目录结构
```
local_wiki/             # 知识库 *.md，懒加载
raw/                    # 原始语料，原则上不用git跟踪
schema/                 # 不同类wiki知识的总结模版
scripts/                # 一些常用的helper脚本工具
skills/                 # 自定义的skill
workspace/              # workspace根目录
|--- <work-item>/       # 单个工作项目录
|------| .workitem.json # 元数据（name / create_at / status）
|------| .session_id    # 当前Code Agent session id
|------| CLAUDE.md      # 本工作项的上下文
|------| setting.json   # per-workitem 模型/服务商 env
MEMORY.md               # 跨工作项长期记忆
CLAUDE.md               # Code Agent规则
README.md               # 项目RAEDME
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