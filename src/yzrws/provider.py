"""Provider 配置读写与校验。

设计参考 doc/provider_design.md。

配置位置（单层）：<workspace>/.config/provider.json

provider.json 的 schema：
  {
    "providers": {
      "<name>": {
        "base_url": "<url>",
        "auth_key": "<token>",
        "model": "<model-name>",
        "agent_types": ["claude-code", "opencode"]  // 可选；缺省时默认全部已注册 engine
      },
      ...
    },
    "default": "<name>"   // 可选
  }

agent_types 的有效值：
  - 任何已注册 engine（"claude-code" / "opencode" 等）
  - 特殊值 "all"：显式声明兼容所有 engine，与不写 agent_types 字段等价
  - "all" 不能与具体 engine 混用（语义模糊）

关键不变量：
  - 写盘使用 atomic_write_json（tempfile + os.replace），写失败不留半截 JSON。
  - 读盘失败（JSON 损坏）抛 ProviderConfigError，由 caller 决定如何报告。
  - 字段校验：name 走正则，base_url 走 urllib.parse 校验，auth_key / model 非空。
  - agent_types 缺省时回退到当前所有已注册 engine（list_engines()），不写死在常量里。
  - 空配置不写出 providers / default 字段，下次 load 后还原为空 ProviderConfig。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from yzrws.workspace import atomic_write_json

# ==================================================================
# 路径与命名
# ==================================================================

# Workspace 级 Provider 配置文件相对路径
WORKSPACE_PROVIDER_REL = Path(".config/provider.json")

# Provider 名称正则：小写字母 / 数字开头，可含连字符和下划线，长度 1-32
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

# agent_types 特殊值：显式声明兼容所有 engine
# 与不写 agent_types 字段等价，但用户可显式选择（补全里可发现）
AGENT_TYPE_ALL = "all"


# ==================================================================
# 异常
# ==================================================================


class ProviderConfigError(Exception):
    """Provider 配置相关的业务异常。"""


# ==================================================================
# 数据类
# ==================================================================


@dataclass(frozen=True)
class Provider:
    """单个 Provider 的配置。

    Attributes:
        name: Provider 名称，对应 providers map 的 key。
        base_url: API 端点。
        auth_key: 认证密钥（明文存储）。
        model: 默认模型名。
        agent_types: 该 provider 的 base_url 适配的 engine 列表；用于防止 workitem
            选中与当前 engine 不兼容的 provider。缺省时回退到所有已注册 engine。
    """

    name: str
    base_url: str
    auth_key: str
    model: str
    agent_types: list[str] = field(default_factory=list)

    def resolved_agent_types(self, all_engine_names: list[str]) -> list[str]:
        """返回该 provider 实际生效的 agent_types。

        缺省时（agent_types 为空列表）回退到 `all_engine_names`；
        否则按原列表返回（保持原顺序，调用方负责去重）。
        """
        if self.agent_types:
            return list(self.agent_types)
        return list(all_engine_names)


@dataclass
class ProviderConfig:
    """workspace 级的 Provider 配置。

    Attributes:
        providers: 名称 → Provider 映射。
        default: 默认 Provider 名称；为 None 表示无默认。
    """

    providers: dict[str, Provider] = field(default_factory=dict)
    default: str | None = None

    def is_empty(self) -> bool:
        """配置是否为空（无任何 Provider，也无 default）。"""
        return not self.providers and self.default is None

    def provider_names(self) -> list[str]:
        """按字母序返回所有 Provider 名称。"""
        return sorted(self.providers.keys())


# ==================================================================
# 路径解析
# ==================================================================


def get_workspace_provider_path(workspace: Path) -> Path:
    """返回 workspace 级 provider.json 的绝对路径。"""
    return workspace / WORKSPACE_PROVIDER_REL


# ==================================================================
# 校验
# ==================================================================


def is_valid_name(name: str) -> bool:
    """校验 Provider 名称是否合法。

    规则（对齐 doc/provider_design.md §Provider 命名规则）：
      - 正则：^[a-z0-9][a-z0-9_-]{0,31}$
    """
    return bool(_NAME_RE.match(name))


def is_valid_base_url(url: str) -> bool:
    """校验 base_url 是否为合法 URL（至少含 scheme + netloc）。"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return bool(parsed.scheme) and bool(parsed.netloc)


def is_valid_agent_type(name: str, all_engine_names: list[str]) -> bool:
    """校验 agent_type 名称是否合法。

    合法的 agent_type 名称可以是：
      - 任一已注册 engine（`all_engine_names` 中的元素）
      - 特殊值 `AGENT_TYPE_ALL`（"all"），显式声明兼容所有 engine

    `name` 必须非空。
    """
    if not name:
        return False
    if name == AGENT_TYPE_ALL:
        return True
    return name in all_engine_names


# ==================================================================
# 读 / 写
# ==================================================================


def load_config(path: Path) -> ProviderConfig:
    """从指定路径加载 Provider 配置。

    Args:
        path: provider.json 的路径；不存在或为空文件时返回空配置。

    Returns:
        ProviderConfig 实例。

    Raises:
        ProviderConfigError: 文件存在但 JSON 损坏 / 字段类型错误。
    """
    if not path.is_file():
        return ProviderConfig()

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ProviderConfigError(f"读取 {path} 失败：{e}") from e

    if not raw.strip():
        return ProviderConfig()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProviderConfigError(f"{path} 不是合法 JSON：{e.msg}") from e

    if not isinstance(data, dict):
        raise ProviderConfigError(f"{path} 顶层必须是 JSON 对象")

    return _parse_config(data, source=path)


def _parse_config(data: dict, *, source: Path) -> ProviderConfig:
    """解析 provider.json 的 dict 表示为 ProviderConfig。"""
    providers_raw = data.get("providers", {})
    if not isinstance(providers_raw, dict):
        raise ProviderConfigError(f"{source} 的 providers 字段必须是对象")

    providers: dict[str, Provider] = {}
    for name, entry in providers_raw.items():
        if not isinstance(entry, dict):
            raise ProviderConfigError(f"{source} 的 providers.{name} 字段必须是对象")
        providers[name] = _parse_provider(name, entry, source)

    default_raw = data.get("default")
    default: str | None
    if default_raw is None:
        default = None
    elif isinstance(default_raw, str):
        default = default_raw
    else:
        raise ProviderConfigError(f"{source} 的 default 字段必须是字符串")

    return ProviderConfig(providers=providers, default=default)


def _parse_provider(name: str, entry: dict, source: Path) -> Provider:
    """解析单个 Provider 条目。"""
    base_url = entry.get("base_url")
    auth_key = entry.get("auth_key")
    model = entry.get("model")

    if not isinstance(base_url, str) or not base_url:
        raise ProviderConfigError(f"{source} 的 providers.{name}.base_url 缺失或为空")
    if not isinstance(auth_key, str) or not auth_key:
        raise ProviderConfigError(f"{source} 的 providers.{name}.auth_key 缺失或为空")
    if not isinstance(model, str) or not model:
        raise ProviderConfigError(f"{source} 的 providers.{name}.model 缺失或为空")

    # agent_types 可选：缺省 / 非 list / 元素非 str 均视为"全部兼容"，记为空列表
    agent_types_raw = entry.get("agent_types")
    agent_types: list[str]
    if agent_types_raw is None:
        agent_types = []
    elif isinstance(agent_types_raw, list) and all(
        isinstance(x, str) and x for x in agent_types_raw
    ):
        agent_types = list(agent_types_raw)
    else:
        raise ProviderConfigError(
            f"{source} 的 providers.{name}.agent_types 必须是字符串列表"
        )

    return Provider(
        name=name,
        base_url=base_url,
        auth_key=auth_key,
        model=model,
        agent_types=agent_types,
    )


def save_config(path: Path, config: ProviderConfig) -> None:
    """将 Provider 配置写入指定路径，原子写。"""
    payload = _config_to_dict(config)
    atomic_write_json(path, payload)


def _config_to_dict(config: ProviderConfig) -> dict:
    """将 ProviderConfig 序列化为 dict。

    空 providers 时不输出 providers 字段；default 缺失时不输出 default 字段。
    agent_types 缺省时（即 dataclass 中为空列表）也不写出——下次 load 同样视为
    "全部兼容"，可避免在引入新 engine 时改动旧 provider.json。
    """
    out: dict = {}
    if config.providers:
        providers_dict: dict[str, dict] = {}
        for name, p in config.providers.items():
            entry: dict = {
                "base_url": p.base_url,
                "auth_key": p.auth_key,
                "model": p.model,
            }
            if p.agent_types:
                entry["agent_types"] = list(p.agent_types)
            providers_dict[name] = entry
        out["providers"] = providers_dict
    if config.default is not None:
        out["default"] = config.default
    return out


# ==================================================================
# 便捷操作（add / remove / set-default 的纯数据层）
# ==================================================================


def add_provider(
    config: ProviderConfig,
    provider: Provider,
    *,
    set_as_default: bool = False,
) -> ProviderConfig:
    """向配置添加一个 Provider，返回新的 ProviderConfig。

    不会原地修改入参 config。

    Args:
        config: 原始配置。
        provider: 待添加的 Provider。
        set_as_default: 是否设为默认；为 True 时强制覆盖现有 default。

    Notes:
        - 重复添加：调用方负责先检查并确认覆盖。
        - 默认值策略：当且仅当明确要求（set_as_default=True）或配置尚无任何 Provider
          且 default 字段为空时，才设置 default。
    """
    new_providers = dict(config.providers)
    new_providers[provider.name] = provider
    new_default = config.default
    if set_as_default or (new_default is None and new_providers):
        new_default = provider.name
    return ProviderConfig(providers=new_providers, default=new_default)


def remove_provider(config: ProviderConfig, name: str) -> ProviderConfig:
    """从配置删除一个 Provider，返回新的 ProviderConfig。

    Args:
        config: 原始配置。
        name: 待删除的 Provider 名称。

    Raises:
        KeyError: 配置中不存在该 Provider。
    """
    if name not in config.providers:
        raise KeyError(name)
    new_providers = {k: v for k, v in config.providers.items() if k != name}
    new_default = config.default
    if new_default == name:
        # 默认值被删除，置空；由调用方决定是否回退到首个 Provider。
        new_default = None
    return ProviderConfig(providers=new_providers, default=new_default)


def set_default(config: ProviderConfig, name: str) -> ProviderConfig:
    """设置默认 Provider，返回新的 ProviderConfig。

    Args:
        config: 原始配置。
        name: 目标 Provider 名称。

    Raises:
        KeyError: 配置中不存在该 Provider。
    """
    if name not in config.providers:
        raise KeyError(name)
    return ProviderConfig(providers=dict(config.providers), default=name)


# ==================================================================
# 回退链解析（yzrws workitem set-model / yzrws workitem start 消费）
# ==================================================================


# ResolvedModel.source 的取值常量
SOURCE_WORKITEM = "workitem"
SOURCE_WORKSPACE_DEFAULT = "workspace_default"
SOURCE_NONE = "none"


@dataclass(frozen=True)
class ResolvedModel:
    """按回退链解析后的最终生效模型配置。

    Attributes:
        base_url: API 端点；可能为 None（表示引擎使用内置默认）。
        auth_key: 认证密钥；可能为 None。
        model: 模型名称；可能为 None。
        provider_name: 解析命中的 Provider 名称（来源层）；None 表示未命中。
        source: "workitem" / "workspace_default" / "none" 三选一。
        agent_types: 该 Provider 兼容的 engine 列表；用于 yzrws workitem start 做兼容性
            警告检查。空列表表示未命中（即 source="none"）。
    """

    base_url: str | None
    auth_key: str | None
    model: str | None
    provider_name: str | None
    source: str
    agent_types: list[str] = field(default_factory=list)


def resolve_model_config(
    setting: dict,
    workspace_config: ProviderConfig,
    all_engine_names: list[str] | None = None,
) -> ResolvedModel:
    """按 doc/provider_design.md §回退链 解析 workitem 最终生效的模型配置。

    Args:
        setting: workitem `setting.json` 的 dict 表示。
        workspace_config: 已加载的 workspace `provider.json`。
        all_engine_names: 已注册 engine 名称列表（用于在 Provider.agent_types
            缺省时回退到全部）。None 时视为"未提供"，Provider.agent_types 缺省
            则保持空列表。

    Returns:
        ResolvedModel 实例。

    Raises:
        KeyError: workitem 指定了 provider，但 workspace 中不存在该 Provider。
    """
    engines = all_engine_names or []

    def _types_of(p: Provider) -> list[str]:
        if p.agent_types:
            return list(p.agent_types)
        return list(engines)

    # 1. workitem setting.json.provider
    workitem_provider = setting.get("provider")
    if isinstance(workitem_provider, str) and workitem_provider:
        p = workspace_config.providers.get(workitem_provider)
        if p is None:
            raise KeyError(workitem_provider)
        return ResolvedModel(
            base_url=p.base_url,
            auth_key=p.auth_key,
            model=p.model,
            provider_name=p.name,
            source=SOURCE_WORKITEM,
            agent_types=_types_of(p),
        )

    # 2. workspace default
    if (
        workspace_config.default
        and workspace_config.default in workspace_config.providers
    ):
        p = workspace_config.providers[workspace_config.default]
        return ResolvedModel(
            base_url=p.base_url,
            auth_key=p.auth_key,
            model=p.model,
            provider_name=p.name,
            source=SOURCE_WORKSPACE_DEFAULT,
            agent_types=_types_of(p),
        )

    # 3. 引擎内置默认
    return ResolvedModel(
        base_url=None,
        auth_key=None,
        model=None,
        provider_name=None,
        source=SOURCE_NONE,
    )
