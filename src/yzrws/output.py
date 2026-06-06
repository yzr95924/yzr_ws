"""自检报告格式化与状态标签常量。

状态标签统一在此集中维护，避免散落在各命令的 print 字符串中。
后续命令（create / list / import 等）应复用这些常量。

报告分块打印：caller 先 print_banner 与 header，调用业务逻辑；
    业务逻辑成功返回 CheckItem 列表时，调用 print_items + footer；
    业务逻辑抛出 fatal 异常时，调用 print_failure。
这样 caller 可以完整控制异常路径上"是否打印路径行"的细节。
"""

import unicodedata
from dataclasses import dataclass
from pathlib import Path

# ---- 状态标签（中文，与设计文档 doc/workspace_init_design.md 对齐）----
STATUS_EXISTS = "已存在"
STATUS_CREATED = "创建"
STATUS_ERROR = "错误"
STATUS_WARN = "警告"


@dataclass(frozen=True)
class CheckItem:
    """单条自检项。

    Attributes:
        name: 人类可读的检查项名称，例如 "workspace 目录" / "metadata.json"。
        path: 对应的物理路径；field 类检查项指向被检查的容器文件。
        kind: "directory" / "file" / "field"，用于报告排序与图标决策。
        status: STATUS_* 常量之一。
        note: 附加说明，例如版本号、损坏原因等；为空时不在报告中显示。
    """

    name: str
    path: Path | None
    kind: str
    status: str
    note: str = ""


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


def print_items(items: list[CheckItem]) -> None:
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


# ---- create workitem 报告 ----

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
    print(f"提示：执行 yzrws start {name} 开始工作")


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


def print_list_table_header(col_widths: dict[str, int]) -> None:
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
    col_widths: dict[str, int],
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
    print("提示：执行 yzrws create workitem <name> 创建工作项")


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


def print_provider_list_header(col_widths: dict[str, int]) -> None:
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
    col_widths: dict[str, int],
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


def print_unused_provider_warning(referenced: list[str], removed_name: str) -> None:
    """删除 Provider 后，若有工作项仍引用该 Provider，打印警告。"""
    if not referenced:
        return
    print()
    print(f"  [{STATUS_WARN}] 以下工作项仍引用 Provider {removed_name!r}：")
    for name in referenced:
        print(f"    - {name}")
    print()
    print("  这些工作项下次 yzrws start 时将沿用其 setting.json 中的 model，")
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
    agent_types: list[str],
) -> None:
    """打印 set-model 成功报告。"""
    print_banner("设置 Workitem 模型")
    print()
    print(f"工作项：{workitem_name}")
    print(f"绑定 Provider：{provider_name}")
    print()
    print(f"  [设置] setting.json.provider = {provider_name!r}")
    print()
    print("生效配置（启动时由 yzrws start 加载）：")
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
    print("下次 yzrws start 将回退到 workspace provider.json 的 default；")
    print("若 workspace 也无 default，则使用引擎内置默认。")
    print()
    print("=== 清除成功 ===")


def print_workitem_show_header() -> None:
    """打印 workitem show 报告的 banner。"""
    print_banner("Workitem 详情")
    print()


def print_workitem_show_section(
    title: str,
    rows: list[tuple[str, str]],
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
    provider_agent_types: list[str],
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
    print(f"     yzrws start {workitem_name} --engine <compatible-engine>")
    print("  2. 选择一个兼容的 provider：")
    print(f"     yzrws workitem set-model {workitem_name} --provider <other>")
    print(
        "  3. 修改该 provider 的 agent_types（先 unset-model，再 model provider add 覆盖）"
    )
