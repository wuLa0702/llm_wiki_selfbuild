"""
工具注册中心 — ToolRegistry

职责：
  - 统一管理 Agent 可用的工具
  - 支持按名注册、注销、启用/禁用
  - 替换硬编码的 P1_TOOLS 列表
  - 为未来动态工具注册（如 MCP 工具加载）提供基础

设计：
  - 单例模式（模块级实例）
  - 注册时自动提取工具名（tool.name 或函数名）
  - 启用/禁用不丢失注册信息，仅控制是否对 LLM 可见
  - 线程安全（dict 操作在 CPython GIL 下天然安全）

用法：
  from src.agent.action.registry import registry
  registry.register(search_wiki)
  registry.register(read_page, enabled=True)
  registry.register(query_graph, enabled=False)
  registry.list_enabled()  # → [search_wiki, read_page]
"""

import logging
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger("agent.registry")


class ToolDefinition:
    """工具注册条目

    Attributes:
        tool: 工具函数或 BaseTool 实例
        name: 工具名称
        enabled: 是否对 LLM 可见
        metadata: 附加元数据（用于分类、权限等）
    """

    def __init__(
        self,
        tool: Any,
        enabled: bool = True,
        metadata: dict | None = None,
    ):
        self.tool = tool
        self.name = self._resolve_name(tool)
        self.enabled = enabled
        self.metadata = metadata or {}

    @staticmethod
    def _resolve_name(tool: Any) -> str:
        """从工具对象解析名称"""
        if isinstance(tool, BaseTool):
            return tool.name
        if hasattr(tool, "name"):
            return tool.name
        if hasattr(tool, "__name__"):
            return tool.__name__
        return str(tool)

    def __repr__(self) -> str:
        return f"ToolDef(name={self.name}, enabled={self.enabled})"


class ToolRegistry:
    """Agent 工具注册中心

    提供统一的工具生命周期管理（注册→启用/禁用→绑定→执行）。
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    # ── 注册与注销 ────────────────────────────────────────────────────────

    def register(
        self,
        tool: Any,
        enabled: bool = True,
        metadata: dict | None = None,
    ) -> str:
        """注册一个工具

        Args:
            tool: @tool 装饰的函数或 BaseTool 实例
            enabled: 是否默认启用
            metadata: 附加元数据

        Returns:
            工具注册名

        Raises:
            ValueError: 同名工具已注册时（不会覆盖，防止意外）
        """
        name = self._resolve_name(tool)
        if name in self._tools:
            raise ValueError(
                f"工具 '{name}' 已注册。如需替换，先 unregister('{name}')"
            )
        self._tools[name] = ToolDefinition(
            tool=tool, enabled=enabled, metadata=metadata
        )
        logger.debug("工具已注册 | name=%s enabled=%s", name, enabled)
        return name

    def unregister(self, name: str) -> None:
        """注销一个工具

        Args:
            name: 工具注册名
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug("工具已注销 | name=%s", name)
        else:
            logger.warning("工具注销跳过（未注册）| name=%s", name)

    # ── 状态管理 ──────────────────────────────────────────────────────────

    def enable(self, name: str) -> None:
        """启用一个已注册的工具"""
        if name in self._tools:
            self._tools[name].enabled = True
            logger.debug("工具已启用 | name=%s", name)

    def disable(self, name: str) -> None:
        """禁用一个已注册的工具"""
        if name in self._tools:
            self._tools[name].enabled = False
            logger.debug("工具已禁用 | name=%s", name)

    def is_enabled(self, name: str) -> bool:
        """检查工具是否已启用"""
        td = self._tools.get(name)
        return td is not None and td.enabled

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get(self, name: str) -> Any | None:
        """按名称获取工具函数"""
        td = self._tools.get(name)
        return td.tool if td else None

    def get_def(self, name: str) -> ToolDefinition | None:
        """按名称获取完整的 ToolDefinition"""
        return self._tools.get(name)

    def list_all(self) -> list[Any]:
        """列出所有已注册的工具（不论启用状态）"""
        return [td.tool for td in self._tools.values()]

    def list_enabled(self) -> list[Any]:
        """列出所有已启用的工具"""
        return [
            td.tool for td in self._tools.values()
            if td.enabled
        ]

    def list_names(self) -> list[str]:
        """列出所有已注册的工具名"""
        return list(self._tools.keys())

    def list_enabled_names(self) -> list[str]:
        """列出所有已启用的工具名"""
        return [
            name for name, td in self._tools.items()
            if td.enabled
        ]

    def count(self) -> int:
        """已注册工具总数"""
        return len(self._tools)

    def count_enabled(self) -> int:
        """已启用工具数"""
        return sum(1 for td in self._tools.values() if td.enabled)

    # ── LLM 绑定 ──────────────────────────────────────────────────────────

    def bind_tools(self, llm: Any) -> Any:
        """将全部已启用工具绑定到 LLM

        Args:
            llm: ChatOpenAI 实例

        Returns:
            绑定了工具的 LLM（使用 llm.bind_tools）
        """
        tools = self.list_enabled()
        if not tools:
            logger.warning("工具绑定：没有已启用的工具")
            return llm
        logger.debug("工具绑定 | count=%d names=%s", len(tools),
                     [t.name if hasattr(t, "name") else str(t) for t in tools])
        return llm.bind_tools(tools)

    # ── 元数据 ────────────────────────────────────────────────────────────

    def get_metadata(self, name: str, key: str = "") -> Any:
        """获取工具元数据

        Args:
            name: 工具名
            key: 元数据键名（空字符串返回全部元数据）

        Returns:
            元数据值，工具不存在返回 None
        """
        td = self._tools.get(name)
        if td is None:
            return None
        if key:
            return td.metadata.get(key)
        return td.metadata

    def set_metadata(self, name: str, metadata: dict) -> None:
        """设置工具元数据"""
        td = self._tools.get(name)
        if td:
            td.metadata.update(metadata)

    @staticmethod
    def _resolve_name(tool: Any) -> str:
        """从工具对象解析名称"""
        if isinstance(tool, BaseTool):
            return tool.name
        if hasattr(tool, "name"):
            return tool.name
        if hasattr(tool, "__name__"):
            return tool.__name__
        return str(tool)


# ── 工具信息查询（API 路由使用） ──────────────────────────────────────────


def get_tool_info() -> list[dict]:
    """返回所有已注册工具的信息列表

    供 API 路由 /v1/agent/tools 使用。

    Returns:
        [{"name": str, "description": str, "enabled": bool, "metadata": dict}]
    """
    global _registry_instance
    reg = _registry_instance
    if reg is None:
        return []
    return [
        {
            'name': td.name,
            'description': getattr(td.tool, 'description', ''),
            'enabled': td.enabled,
            'metadata': td.metadata,
        }
        for td in reg._tools.values()
    ]


# ── 模块级单例 ──────────────────────────────────────────────────────────────

_registry_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例

    用于避免模块重载时的状态丢失。
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance


# 默认单例（可直接 import registry）
registry = get_tool_registry()


# ── 默认工具初始化 ──────────────────────────────────────────────────────────


def init_default_tools() -> None:
    """注册项目的默认工具到全局注册中心

    等价于原来的 P1_TOOLS = [search_wiki, read_page]
    在模块导入时自动执行，确保从 registry 获取的工具始终包含默认集。

    metadata.requires_approval — 工具风险分级标记（方案 A，渐进式维护）：
      False — 只读查询工具，调用前直接放行，不弹审批
      省略  — 新工具默认按需审批（fail-closed，确认只读后补标 False）
      未来写操作工具必须显式标记 True（或保持省略），获得审批保护。
    """
    from src.agent import constants as C
    from src.agent.action.tools import read_page, search_wiki

    for tool in (search_wiki, read_page):
        try:
            registry.register(tool, metadata={C.METADATA_REQUIRES_APPROVAL: False})
        except ValueError:
            pass  # 已注册则跳过（幂等）


def get_tool_info() -> list[dict]:
    """获取所有启用工具的元数据列表（供 API 展示）

    返回每个工具的名称、描述，前端可渲染为工具面板。
    """
    from src.agent import constants as C

    return [
        {
            C.FIELD_NAME: t.name if hasattr(t, "name") else str(t),
            "description": t.description if hasattr(t, "description") else "",
        }
        for t in registry.list_enabled()
    ]


# 模块加载时自动注册默认工具
init_default_tools()
