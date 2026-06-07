"""workitem 创建流程的公共 helper。

从原 commands/create.py 提取；create 与 start 共享。
原 create.py 是唯一来源，2026-06 重构时把"创建工作项"流程的纯函数 / 常量
提到独立模块，去掉 `_` 前缀作为公共 API。
"""

from __future__ import annotations

import json
from pathlib import Path

from yzrws.workspace import atomic_write_json, atomic_write_text, now_iso

# 未指定 --engine 时的回退链：CLI 参数 → 用户级全局配置 → 兜底值
DEFAULT_ENGINE = "claude-code"

# recent_workitems 保留的最大条目数
MAX_RECENT_WORKITEMS = 5

# CLAUDE.md 模板内容（{name} 占位符由创建工作项时替换）
_CLAUDE_MD_TEMPLATE = """\
# {name}

> 本文件是该工作项的上下文说明，Code Agent 启动时自动加载。

## 目标

<!-- 该工作项要达成什么目标？ -->

## 关键决策

<!-- 已做出的重要设计决策及其理由 -->

## 约束条件

<!-- 技术约束、时间约束、依赖限制等 -->

## 相关资源

<!-- 关联的设计文档、参考资料、外部链接 -->
"""


# ==================================================================
# 前置检查
# ==================================================================


def check_path_exists(
    target: Path,
    name: str,  # noqa: ARG001
    workspace_path: Path,  # noqa: ARG001
) -> str | None:
    """检查目标路径是否已存在。

    返回值：
      - None：不存在，可以继续创建
      - "directory"：同名目录已存在（幂等场景）
      - "file"：同名文件已存在（错误场景）
    """
    if target.is_dir():
        return "directory"
    if target.exists():
        return "file"
    return None


# ==================================================================
# 引擎解析
# ==================================================================


def resolve_engine(cli_engine: str | None) -> str:
    """确定引擎名称，优先级从高到低：

    1. --engine 命令行参数
    2. ~/.config/yzrws/config.json 中的 default_engine
    3. 兜底值 DEFAULT_ENGINE（"claude-code"）

    对齐 doc/workitem_create_design.md §setting.json 中的引擎确定逻辑。
    """
    if cli_engine:
        return cli_engine

    # 读取用户级全局配置
    config_path = Path("~/.config/yzrws/config.json").expanduser()
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            default_engine = data.get("default_engine")
            if isinstance(default_engine, str) and default_engine:
                return default_engine
        except (json.JSONDecodeError, OSError):
            pass

    return DEFAULT_ENGINE


# ==================================================================
# 目录与文件创建
# ==================================================================


def create_directories(
    target: Path,
    name: str,
) -> list[tuple[str, str]]:
    """创建工作项目录结构，返回 [(action, item)] 列表用于报告。

    创建：
      - <name>/
      - <name>/raw/
      - <name>/local_wiki/（含 .gitkeep）
    """
    items: list[tuple[str, str]] = []

    target.mkdir(parents=True, exist_ok=True)
    items.append(("创建", f"{name}/"))

    raw_dir = target / "raw"
    raw_dir.mkdir(exist_ok=True)
    items.append(("创建", f"{name}/raw/"))

    wiki_dir = target / "local_wiki"
    wiki_dir.mkdir(exist_ok=True)
    # local_wiki/ 下放 .gitkeep（知识文件可能需要版本追踪）；
    # raw/ 不放（原始语料通常不纳入版本控制，符合 README 约定）
    gitkeep = wiki_dir / ".gitkeep"
    if not gitkeep.exists():
        atomic_write_text(gitkeep, "")
    items.append(("创建", f"{name}/local_wiki/"))

    return items


def write_initial_files(
    target: Path,
    name: str,
    engine: str,
) -> list[tuple[str, str]]:
    """写入初始文件，返回 [(action, item)] 列表用于报告。

    写入：
      - workitem.json  工作项元数据
      - setting.json   引擎配置
      - CLAUDE.md      工作项上下文（带模板引导）
    """
    items: list[tuple[str, str]] = []
    now = now_iso()

    # workitem.json
    workitem_data = {
        "name": name,
        "created_at": now,
        "status": "active",
    }
    atomic_write_json(target / "workitem.json", workitem_data)
    items.append(("创建", f"{name}/workitem.json"))

    # setting.json
    setting_data = {
        "engine": engine,
        "model": None,
        "provider": None,
        "outline": None,
        "env": {},
    }
    atomic_write_json(target / "setting.json", setting_data)
    items.append(("创建", f"{name}/setting.json"))

    # CLAUDE.md
    claude_content = _CLAUDE_MD_TEMPLATE.format(name=name)
    atomic_write_text(target / "CLAUDE.md", claude_content)
    items.append(("创建", f"{name}/CLAUDE.md"))

    return items


# ==================================================================
# 元数据同步
# ==================================================================


def update_metadata(workspace_path: Path, name: str) -> tuple[int, int]:
    """更新 workspace 级 metadata.json，返回 (count_before, count_after)。

    更新内容（对齐 doc/workitem_create_design.md §元数据同步）：
      - stats.workitem_count += 1
      - stats.active_workitem_count += 1
      - recent_workitems 追加新条目，保持 top 5
      - updated_at 刷新

    metadata.json 可能缺少 stats / recent_workitems 字段（init 只写入最小集），
    此函数会自动初始化缺失字段。
    """
    metadata_path = workspace_path / "metadata.json"
    if not metadata_path.is_file():
        # 不应到达此分支（前置检查已验证 workspace 初始化）
        return 0, 1

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # JSON 损坏时以空 dict 重建，保证创建流程不中断
        data = {}

    # 确保 stats 字段存在
    stats = data.get("stats")
    if not isinstance(stats, dict):
        stats = {}
        data["stats"] = stats

    # 更新计数
    count_before = stats.get("workitem_count", 0)
    stats["workitem_count"] = count_before + 1
    stats["active_workitem_count"] = stats.get("active_workitem_count", 0) + 1

    # 更新 recent_workitems
    now = now_iso()
    recent = data.get("recent_workitems")
    if not isinstance(recent, list):
        recent = []
    new_entry = {
        "name": name,
        "status": "active",
        "last_active_at": now,
    }
    recent.insert(0, new_entry)
    data["recent_workitems"] = recent[:MAX_RECENT_WORKITEMS]

    # 刷新 updated_at
    data["updated_at"] = now

    atomic_write_json(metadata_path, data)
    return count_before, count_before + 1
