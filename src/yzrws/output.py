"""自检报告格式化与状态标签常量。

状态标签统一在此集中维护，避免散落在各命令的 print 字符串中。
后续命令（create / list / import 等）应复用这些常量。

报告分块打印：caller 先 print_banner 与 header，调用业务逻辑；
    业务逻辑成功返回 CheckItem 列表时，调用 print_items + footer；
    业务逻辑抛出 fatal 异常时，调用 print_failure。
这样 caller 可以完整控制异常路径上"是否打印路径行"的细节。
"""

import unicodedata

from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---- 状态标签（中文，与设计文档 doc/workspace_init_design.md 对齐）----
STATUS_EXISTS = "已存在"
STATUS_CREATED = "创建"
STATUS_ERROR = "错误"
STATUS_WARN = "警告"


class CheckItem:
    """单条自检项。

    Attributes:
        name: 人类可读的检查项名称，例如 "workspace 目录" / "metadata.json"。
        path: 对应的物理路径；field 类检查项指向被检查的容器文件。
        kind: "directory" / "file" / "field"，用于报告排序与图标决策。
        status: STATUS_* 常量之一。
        note: 附加说明，例如版本号、损坏原因等；为空时不在报告中显示。
    """

    __slots__ = ("name", "path", "kind", "status", "note")

    def __init__(
        self,
        name,  # type: str
        path,  # type: Optional[Path]
        kind,  # type: str
        status,  # type: str
        note="",  # type: str
    ):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "note", note)

    def __setattr__(self, key, value):
        raise AttributeError(f"cannot assign to field {key!r}")

    def __delattr__(self, key):
        raise AttributeError(f"cannot delete field {key!r}")

    def _replace(self, **kwargs):
        """返回一个新 CheckItem，替换指定字段。

        等价于 dataclasses.replace()，供 workspace.py 使用。
        """
        return CheckItem(
            name=kwargs.get("name", self.name),
            path=kwargs.get("path", self.path),
            kind=kwargs.get("kind", self.kind),
            status=kwargs.get("status", self.status),
            note=kwargs.get("note", self.note),
        )


def print_banner(title: str) -> None:
    """打印顶级 banner：=== title ===。"""
    print(f"=== {title} ===")


def _display_width(text: str) -> int:
    """计算字符串在等宽终端里的显示宽度（CJK 算 2 列）。"""
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def print_items(items: List[CheckItem]) -> None:
    """逐行打印自检项，不含头尾装饰。

    状态标签按显示宽度对齐到本批 items 中的最宽标签，
    使 name 列起点一致（与设计文档样例一致）。
    """
    if not items:
        return
    max_tag_width = max(_display_width(f"[{item.status}]") for item in items)
    for item in items:
        tag = f"[{item.status}]"
        pad = " " * (max_tag_width - _display_width(tag))
        if item.note:
            print(f"  {tag}{pad} {item.name}  {item.note}")
        else:
            print(f"  {tag}{pad} {item.name}")


def print_init_footer(has_error: bool) -> None:
    """打印 init 报告底部状态行。"""
    if has_error:
        print("=== 初始化失败 ===")
    else:
        print("=== 自检通过，workspace 已就绪 ===")


def print_failure(message: str, hint: str = "") -> None:
    """打印致命错误信息（前置检查失败场景）。

    输出格式与设计文档 doc/workspace_init_design.md 第 267-278 行的样例对齐：
        [错误] <message>
               <hint>   (仅当 hint 非空)

    === 初始化失败 ===
    """
    print(f"  [{STATUS_ERROR}] {message}")
    if hint:
        print(f"         {hint}")
    print()
    print("=== 初始化失败 ===")


# ---- workitem create 报告 ----

# 设计参考 doc/workitem_create_design.md §输出示例。


def print_create_report_header(name: str, workspace_path: Path, engine: str) -> None:
    """打印创建工作项报告的 banner 与基本信息。"""
    print_banner("创建工作项")
    print()
    print(f"名称：{name}")
    print(f"路径：{workspace_path / name}")
    print(f"引擎：{engine}")
    print()


def print_create_item(action: str, item: str) -> None:
    """打印单条创建 / 更新操作行。

    action 为"创建"或"更新"等状态词；item 为文件 / 目录的相对路径描述。
    """
    tag = f"[{action}]"
    # 对齐到 [创建] / [更新] 的最宽标签（当前两者等宽，均为 4 CJK 字符）
    max_tag_width = _display_width(f"[{STATUS_CREATED}]")
    pad = " " * (max_tag_width - _display_width(tag))
    print(f"  {tag}{pad} {item}")


def print_metadata_update(count_before: int, count_after: int) -> None:
    """打印 metadata.json 更新行，含 workitem_count 变化量。"""
    print_create_item(
        "更新",
        f"metadata.json (workitem_count: {count_before} → {count_after})",
    )


def print_create_footer(name: str) -> None:
    """打印创建工作项报告的底部成功行。"""
    print()
    print("=== 创建成功 ===")
    print()
    print(f"提示：执行 yzrws workitem start {name} 开始工作")


def print_workitem_exists(name: str, workspace_path: Path) -> None:
    """打印"工作项已存在"的幂等提示（退出码 0）。"""
    print_banner("创建工作项")
    print()
    print(f"工作项 {name} 已存在：{workspace_path / name}")


def print_workitem_name_invalid(name: str) -> None:
    """打印名称不合法的错误提示，含命名规则说明。"""
    print(f'[{STATUS_ERROR}] 工作项名称不合法："{name}"')
    print()
    print("命名规则：")
    print("  • 只允许小写字母、数字、连字符（-）和下划线（_）")
    print("  • 长度 1-64 个字符")
    print("  • 不能以连字符或下划线开头")
    print("  • 不能是保留名称（knowledge, config, raw）")
    print()
    print("示例：my-task, api_refactor, v2-migration")


def print_workspace_not_initialized(workspace_path: Path) -> None:
    """打印 workspace 未初始化的错误提示。"""
    metadata_path = workspace_path / "metadata.json"
    print(f"[{STATUS_ERROR}] 工作区未初始化：{metadata_path} 不存在")
    print()
    print("请先执行以下命令初始化工作区：")
    print("  yzrws init")


# ---- list workitem 报告 ----


def _pad(text: str, width: int) -> str:
    """用空格将 text 填充到指定显示宽度（CJK 感知）。"""
    current = _display_width(text)
    return text + " " * max(0, width - current)


def print_list_header() -> None:
    """打印 list 命令的 banner。"""
    print_banner("工作项列表")
    print()


def print_list_table_header(col_widths: Dict[str, int]) -> None:
    """打印表头行（列名），列宽由 col_widths 指定。"""
    row = "  ".join(
        _pad(label, col_widths[key])
        for key, label in [
            ("name", "NAME"),
            ("status", "STATUS"),
            ("engine", "ENGINE"),
            ("created", "CREATED"),
        ]
    )
    print(row)
    print(
        "  ".join("-" * col_widths[k] for k in ("name", "status", "engine", "created"))
    )


def print_list_row(
    name: str,
    status: str,
    engine: str,
    created: str,
    col_widths: Dict[str, int],
) -> None:
    """打印单行工作项数据，列宽对齐 col_widths。"""
    row = "  ".join(
        _pad(val, col_widths[key])
        for key, val in [
            ("name", name),
            ("status", status),
            ("engine", engine),
            ("created", created),
        ]
    )
    print(row)


def print_list_empty() -> None:
    """打印"尚无工作项"的提示信息。"""
    print("尚未创建任何工作项。")
    print()
    print("提示：执行 yzrws workitem create <name> 创建工作项")


# ---- model provider 报告 ----

# 设计参考 doc/provider_design.md §创建流程 / §管理命令。


def print_provider_workspace_not_initialized(workspace_path) -> None:
    """打印 workspace 未初始化（Provider 操作的致命前置条件）。"""
    metadata_path = workspace_path / "metadata.json"
    print(f"[{STATUS_ERROR}] 工作区未初始化：{metadata_path} 不存在")
    print()
    print("请先执行以下命令初始化工作区：")
    print("  yzrws init")


def print_provider_empty() -> None:
    """打印"尚无 Provider 配置"的提示。"""
    print("尚未配置任何 Provider。")
    print()
    print("提示：执行 yzrws model provider add 添加一个 Provider")


def print_provider_list_header(col_widths: Dict[str, int]) -> None:
    """打印 provider list 表格的表头与分隔线。

    列：NAME / BASE_URL / MODEL / AGENT_TYPES / DEFAULT。
    DEFAULT 列用 `★` / 空标记，不参与对齐。
    """
    row = "  ".join(
        _pad(label, col_widths[key])
        for key, label in [
            ("name", "NAME"),
            ("base_url", "BASE_URL"),
            ("model", "MODEL"),
            ("agent_types", "AGENT_TYPES"),
        ]
    )
    print(row)
    print(
        "  ".join(
            "-" * col_widths[k] for k in ("name", "base_url", "model", "agent_types")
        )
    )


def print_provider_list_row(
    *,
    name: str,
    base_url: str,
    model: str,
    agent_types_display: str,
    is_default: bool,
    col_widths: Dict[str, int],
) -> None:
    """打印 provider list 的单行数据，DEFAULT 列用 `★` 标记。"""
    row = "  ".join(
        _pad(val, col_widths[key])
        for key, val in [
            ("name", name),
            ("base_url", base_url),
            ("model", model),
            ("agent_types", agent_types_display),
        ]
    )
    default_marker = "★ 默认" if is_default else ""
    print(f"{row}  {default_marker}")


def print_provider_added(
    *,
    name: str,
    is_default: bool,
    is_first: bool,
    set_default_flag: bool,
) -> None:
    """打印新增 Provider 后的成功报告（不打印 banner，由 caller 控制）。"""
    print(f"  [新增] Provider {name!r}")
    if is_default:
        if is_first:
            print("  [默认] 首个 Provider，已自动设为默认")
        elif set_default_flag:
            print("  [默认] 已设为默认 Provider")
    print()
    print("=== 添加成功 ===")


def print_provider_duplicate_confirm(name: str, target_path) -> bool:
    """提示同名 Provider 已存在，询问是否覆盖。返回 True 表示确认覆盖。

    调用方需先打印 banner 与目标文件信息；此处只负责警告行与确认交互。
    """
    print(f"  [{STATUS_WARN}] Provider {name!r} 已存在于 {target_path}")
    while True:
        try:
            ans = input("确认覆盖？[y/N]: ").strip().lower()
        except EOFError:
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False
        print("请输入 y 或 n")


def print_provider_removed(name: str, target_path, *, was_default: bool) -> None:
    """打印删除 Provider 后的报告（不打印 banner，由 caller 控制）。"""
    print(f"  [删除] Provider {name!r}")
    if was_default:
        print(f"  [{STATUS_WARN}] 该 Provider 是当前默认 Provider，default 已清空")
    print()
    print("=== 删除成功 ===")


def print_unused_provider_warning(referenced: List[str], removed_name: str) -> None:
    """删除 Provider 后，若有工作项仍引用该 Provider，打印警告。"""
    if not referenced:
        return
    print()
    print(f"  [{STATUS_WARN}] 以下工作项仍引用 Provider {removed_name!r}：")
    for name in referenced:
        print(f"    - {name}")
    print()
    print("  这些工作项下次 yzrws workitem start 时将沿用其 setting.json 中的 model，")
    print("  并回退到该层其它 Provider / 上层 default；如需解除引用，")
    print("  可使用 yzrws config set provider <name> 显式重设。")


def print_user_aborted(action: str) -> None:
    """用户中断 / 拒绝确认时的提示。"""
    print()
    print(f"{action} 已取消。")


# ---- workitem 配置 报告 ----

# 设计参考 doc/command_design.md §配置 workitem。


def print_workitem_set_model(
    *,
    workitem_name: str,
    provider_name: str,
    model: str,
    base_url: str,
    agent_types: List[str],
) -> None:
    """打印 set-model 成功报告。"""
    print_banner("设置 Workitem 模型")
    print()
    print(f"工作项：{workitem_name}")
    print(f"绑定 Provider：{provider_name}")
    print()
    print(f"  [设置] setting.json.provider = {provider_name!r}")
    print()
    print("生效配置（启动时由 yzrws workitem start 加载）：")
    print(f"  - model       ：{model}")
    print(f"  - base_url    ：{base_url}")
    print(f"  - agent_types ：{', '.join(agent_types)}")
    print()
    print("=== 设置成功 ===")


def print_workitem_unset_model(workitem_name: str) -> None:
    """打印 unset-model 成功报告。"""
    print_banner("清除 Workitem 模型绑定")
    print()
    print(f"工作项：{workitem_name}")
    print()
    print("  [清除] setting.json.provider = null")
    print()
    print("下次 yzrws workitem start 将回退到 workspace provider.json 的 default；")
    print("若 workspace 也无 default，则使用引擎内置默认。")
    print()
    print("=== 清除成功 ===")


def print_workitem_show_header() -> None:
    """打印 workitem show 报告的 banner。"""
    print_banner("Workitem 详情")
    print()


def print_workitem_show_section(
    title: str,
    rows: List[Tuple[str, str]],
) -> None:
    """打印 workitem show 的单节键值对。

    格式：
        <title>:
          KEY          VALUE
          ───────────  ──────────────────────────
          engine       claude-code
          ...
    """
    print(f"{title}：")
    if not rows:
        print("  (无)")
        print()
        return
    key_width = max(_display_width(k) for k, _ in rows)
    print("  " + _pad("KEY", key_width) + "  " + "VALUE")
    print("  " + "-" * key_width + "  " + "-" * 40)
    for k, v in rows:
        print("  " + _pad(k, key_width) + "  " + v)
    print()


def print_workitem_not_found(name: str, workspace_path) -> None:
    """打印"工作项不存在"错误（退出码 1）。"""
    target = workspace_path / name
    print(f"[{STATUS_ERROR}] 工作项不存在：{target}")
    print()
    print("提示：执行 yzrws list 查看已有工作项")


def print_provider_not_found_for_set_model(provider_name: str, workspace_path) -> None:
    """打印 set-model 时指定 provider 不存在的错误。"""
    print(f"[{STATUS_ERROR}] Provider {provider_name!r} 不存在于 workspace")
    print()
    print("提示：执行 yzrws model provider list 查看已配置的 Provider")


def print_provider_incompatible_for_engine(
    *,
    provider_name: str,
    workitem_name: str,
    workitem_engine: str,
    provider_agent_types: List[str],
) -> None:
    """打印 set-model 时 provider 与 workitem engine 不兼容的错误。"""
    compatible = ", ".join(provider_agent_types) if provider_agent_types else "（无）"
    print(f"[{STATUS_ERROR}] Provider {provider_name!r} 不兼容当前 workitem 的 engine")
    print()
    print(f"  workitem：{workitem_name}")
    print(f"  当前 engine：{workitem_engine}")
    print(f"  Provider {provider_name!r} 仅支持：{compatible}")
    print()
    print("可执行以下操作之一：")
    print("  1. 切换 workitem 的 engine 后重试：")
    print(f"     yzrws workitem start {workitem_name} --engine <compatible-engine>")
    print("  2. 选择一个兼容的 provider：")
    print(f"     yzrws workitem set-model {workitem_name} --provider <other>")
    print(
        "  3. 修改该 provider 的 agent_types（先 unset-model，再 model provider add 覆盖）"
    )


# ---- session 管理报告 ----

# 设计参考 doc/session_design.md 与 doc/command_design.md §管理 session。


def _format_session_updated(updated_at: str) -> str:
    """把 ISO 8601 时间戳格式化为 'YYYY-MM-DD HH:MM:SS'；空时返回 '—'。"""
    if not updated_at:
        return "—"
    # ISO 8601 形如 2026-06-08T10:00:00+08:00；按 T 切并取前两段
    head = updated_at.split("T", 1)
    if len(head) != 2:
        return updated_at
    date_part = head[0]
    time_part = head[1].split("+", 1)[0].split("-", 1)[0].split("Z", 1)[0]
    if not time_part:
        return date_part
    return f"{date_part} {time_part}"


def print_session_list_header(col_widths: Dict[str, int]) -> None:
    """打印 session list 表头与分隔线。列：NAME / TITLE / ENGINE / UPDATED。"""
    row = "  ".join(
        _pad(label, col_widths[key])
        for key, label in [
            ("name", "NAME"),
            ("title", "TITLE"),
            ("engine", "ENGINE"),
            ("updated", "UPDATED"),
        ]
    )
    print(row)
    print(
        "  ".join("-" * col_widths[k] for k in ("name", "title", "engine", "updated"))
    )


def print_session_list_row(
    *,
    name: str,
    title: str,
    engine: str,
    updated_at: str,
    is_current: bool,
    col_widths: Dict[str, int],
) -> None:
    """打印 session list 单行；``is_current=True`` 时首列加 '★ ' 前缀。"""
    name_display = f"★ {name}" if is_current else f"  {name}"
    row = "  ".join(
        _pad(val, col_widths[key])
        for key, val in [
            ("name", name_display),
            ("title", title or "—"),
            ("engine", engine or "—"),
            ("updated", _format_session_updated(updated_at)),
        ]
    )
    print(row)


def print_session_list_empty(current: Optional[str]) -> None:
    """无 session 时的提示。current 为 None 时说明 '尚无 current 指针'。"""
    print("  （尚无 session）")
    print()
    if current is None:
        print("当前 current 指针：（未设置）")
    else:
        print(f"当前 current 指针：{current}")
    print()
    print("提示：执行 yzrws workitem start <workitem> 创建 default session")
    print("      或 yzrws workitem start <workitem> --session <name> 指定 session 名")


def print_session_list_footer(current: Optional[str]) -> None:
    """list 末尾的 current 指针说明行。"""
    if current is None:
        print()
        print("当前 current 指针：（未设置）")
    else:
        print()
        print(f"当前 current 指针：{current}")


def print_session_show(
    *,
    workitem_name: str,
    session_name: str,
    engine: str,
    session_id: str,
    status: str,
    title: str,
    model: str,
    provider: str,
    created_at: str,
    updated_at: str,
    resume_count: int,
    is_current: bool,
) -> None:
    """打印 session 详情（三段式：基本信息 / 会话元数据 / 状态）。"""
    print_banner("Workitem Session 详情")
    print()
    print(f"工作项：{workitem_name}")
    print(f"Session：{session_name}")
    if is_current:
        print("当前 current：★ 是")
    print()

    basic_rows: List[Tuple[str, str]] = [
        ("name", session_name),
        ("title", title or "—"),
        ("engine", engine or "—"),
        ("session_id", session_id or "—"),
    ]
    print_workitem_show_section("基本信息", basic_rows)

    meta_rows: List[Tuple[str, str]] = [
        ("model", model or "—"),
        ("provider", provider or "—"),
        ("created_at", created_at or "—"),
        ("updated_at", updated_at or "—"),
    ]
    print_workitem_show_section("会话元数据", meta_rows)

    status_rows: List[Tuple[str, str]] = [
        ("status", status or "—"),
        ("resume_count", str(resume_count)),
    ]
    print_workitem_show_section("状态", status_rows)


def print_session_removed(
    *,
    workitem_name: str,
    session_name: str,
    was_current: bool,
) -> None:
    """打印删除 session 成功报告。"""
    print_banner("删除 Session")
    print()
    print(f"工作项：{workitem_name}")
    print(f"Session：{session_name}")
    print()
    print(f"  [删除] sessions/{session_name}.json")
    if was_current:
        print(f"  [{STATUS_WARN}] 该 session 是当前 current 指针，已清空")
        print()
        print("下次 yzrws workitem start 将创建 default session。")
    print()
    print("=== 删除成功 ===")


def print_session_use_changed(
    *,
    workitem_name: str,
    old: Optional[str],
    new: str,
) -> None:
    """打印切换 current 指针成功报告。"""
    print_banner("切换 Session current 指针")
    print()
    print(f"工作项：{workitem_name}")
    print(f"原 current：{old or '（未设置）'}")
    print(f"新 current：{new}")
    print()
    print(f"  [设置] session.json.current = {new!r}")
    print()
    print("=== 切换成功 ===")


def print_session_remove_confirm(
    *,
    workitem_name: str,
    session_name: str,
    is_current: bool,
) -> bool:
    """删除 session 前的交互式确认。返回 True = 确认删除。

    与 ``print_provider_duplicate_confirm`` 风格一致。
    """
    print(f"  [{STATUS_WARN}] 即将删除 session {session_name!r}")
    if is_current:
        print(
            f"  [{STATUS_WARN}] 该 session 是当前 current 指针，"
            "删除后下次 yzrws workitem start 将创建 default"
        )
    while True:
        try:
            ans = input("确认删除？[y/N]: ").strip().lower()
        except EOFError:
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False
        print("请输入 y 或 n")


def print_session_name_invalid(name: str) -> None:
    """打印 session 名不合法错误。"""
    print(f"[{STATUS_ERROR}] Session 名不合法：{name!r}")
    print()
    print("命名规则：")
    print("  • 长度 1-32 个字符")
    print("  • 只允许小写字母、数字、连字符（-）和下划线（_）")
    print("  • 必须以小写字母或数字开头")
    print()
    print("示例：default, explore-outline, fix-bug-2026-06")


def print_session_not_found(
    *,
    workitem_name: str,
    session_name: str,
) -> None:
    """打印 session 不存在错误。"""
    print(f"[{STATUS_ERROR}] Session {session_name!r} 不存在于工作项 {workitem_name!r}")
    print()
    print(f"提示：执行 yzrws workitem session list {workitem_name} 查看已有 session")


def print_session_engine_mismatch(
    *,
    workitem_name: str,
    session_name: str,
    session_engine: str,
    requested_engine: str,
) -> None:
    """打印 start 时 --engine 与现存 session.engine 冲突的错误。"""
    print(
        f"[{STATUS_ERROR}] Session {session_name!r} 的 engine {session_engine!r} "
        f"与指定的 --engine {requested_engine!r} 不一致"
    )
    print()
    print(f"  workitem：{workitem_name}")
    print(f"  session.engine：{session_engine}")
    print(f"  --engine     ：{requested_engine}")
    print()
    print("可执行以下操作之一：")
    print("  1. 去掉 --engine 参数，沿用 session 自带的 engine：")
    print(f"     yzrws workitem start {workitem_name} --session {session_name}")
    print("  2. 切换到与 session.engine 一致的 engine：")
    print(
        f"     yzrws workitem start {workitem_name} --session {session_name} "
        f"--engine {session_engine}"
    )
    print("  3. 创建新的同名 session（先删后建）：")
    print(f"     yzrws workitem session remove {workitem_name} {session_name}")
