"""
Agent 配置常量 — 所有魔法值的唯一真相源

规范：
  - 所有硬编码字面量（数字、字符串、默认值）必须在此定义
  - agent.py / tools.py 中禁止出现裸字面量（0 和空字符串例外）
  - 按类别分组，每组上方有注释标题
"""

# ═══════════════════════════════════════════════════════════════════════════════
# LLM 配置
# ═══════════════════════════════════════════════════════════════════════════════

# 环境变量键名
ENV_DEEPSEEK_MODEL = "DEEPSEEK_MODEL"
ENV_DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
ENV_DEEPSEEK_API_BASE = "DEEPSEEK_API_BASE"

# LLM 默认值
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_API_BASE = "https://api.deepseek.com/v1"
LLM_TIMEOUT = 15
LLM_MAX_RETRIES = 1


# ═══════════════════════════════════════════════════════════════════════════════
# 对话窗口
# ═══════════════════════════════════════════════════════════════════════════════

# 硬窗口保护：超出此轮数的历史被丢弃，P2 用 ConversationSummaryMemory 替代
MAX_MESSAGE_TURNS = 20

# Agent Checkpointer 持久化数据库路径（MemorySaver 纯内存不持久）
# 持久化由 persistence.py 的 SQLite 层负责
PERSISTENCE_DB_PATH = "agent_persistence.db"


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph 图结构
# ═══════════════════════════════════════════════════════════════════════════════

# 图节点名（必须与 add_node 的第一个参数完全一致）
NODE_AGENT = "agent"
NODE_TOOLS = "tools"

# 状态键
STATE_MESSAGES = "messages"

# Config 键
CONFIG_CONFIGURABLE = "configurable"
CONFIG_THREAD_ID = "thread_id"

# astream_events 版本
ASTREAM_EVENTS_VERSION = "v1"


# ═══════════════════════════════════════════════════════════════════════════════
# SSE 事件协议
# ═══════════════════════════════════════════════════════════════════════════════

# 事件类型（yield 的 type 字段值）
EVENT_TOKEN = "token"
EVENT_TOOL_START = "tool_start"
EVENT_TOOL_END = "tool_end"
EVENT_DONE = "done"
EVENT_ERROR = "error"

# 事件字段名
FIELD_TYPE = "type"
FIELD_ROLE = "role"
FIELD_CONTENT = "content"
FIELD_TOOL = "tool"
FIELD_INPUT = "input"
FIELD_OUTPUT = "output"
FIELD_SOURCES = "sources"
FIELD_MESSAGE = "message"
FIELD_EVENT = "event"
FIELD_NAME = "name"
FIELD_DATA = "data"
FIELD_CHUNK = "chunk"
FIELD_RUN_ID = "run_id"

# 工具输出截断长度
TOOL_OUTPUT_DISPLAY_CHARS = 500


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph astream_events kind
# ═══════════════════════════════════════════════════════════════════════════════

KIND_CHAT_MODEL_STREAM = "on_chat_model_stream"
KIND_TOOL_START = "on_tool_start"
KIND_TOOL_END = "on_tool_end"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 消息角色
# ═══════════════════════════════════════════════════════════════════════════════

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

# 默认消息角色（前端未传 role 时的兜底）
DEFAULT_ROLE = ROLE_USER


# ═══════════════════════════════════════════════════════════════════════════════
# 工具配置
# ═══════════════════════════════════════════════════════════════════════════════

# Wiki 搜索
WIKI_DIR = "wiki"
SEARCH_LIMIT = 10
SNIPPET_MAX_CHARS = 200
SCORE_FORMAT = ".2f"
NO_MATCHES_MESSAGE = "未找到匹配的页面"

# 页面读取
READ_PAGE_MAX_CHARS = 4000
TRUNCATION_MARKER = "\n\n...（内容已截断）"
EMPTY_CONTENT_MESSAGE = "（页面内容为空）"

# 图谱查询
MATCHED_NODES_LIMIT = 5
NEIGHBOR_NODES_LIMIT = 8

# Wiki 路径正则（从 tool 输出中提取 `xxx.md` 引用）
WIKI_PATH_REGEX = r'`([^`]+\.md)`'


# ═══════════════════════════════════════════════════════════════════════════════
# 错误消息模板
# ═══════════════════════════════════════════════════════════════════════════════

ERROR_AGENT_FAILED = "Agent 调用失败: {}"
ERROR_EMPTY_MESSAGES = "消息列表为空"
ERROR_SEARCH_FAILED = "搜索失败：{}"
ERROR_PATH_UNAUTHORIZED = "路径越权：{}"
ERROR_PAGE_NOT_FOUND = "页面不存在：{}"
ERROR_READ_FAILED = "读取失败：{}"
ERROR_GRAPH_FAILED = "图谱查询失败：{}"
ERROR_NO_ENTITIES = "未找到相关实体。知识库共有 {} 个页面。"
ERROR_NO_ENTITIES_WITH_COMMUNITIES = (
    "未找到与问题直接相关的实体。知识库共有 {} 个页面。\n\n社区分布：\n{}"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 日志消息模板
# ═══════════════════════════════════════════════════════════════════════════════

# Agent
LOG_AGENT_BUILT = "Agent 构建完成 | tools=%s"
LOG_STREAM_FAILED = "Agent 流式调用失败 | error=%s"
LOG_SESSION_FAILED = "Agent 会话流式调用失败 | thread=%s error=%s"
LOG_SESSION_FIRST_TURN = "会话首轮 | thread=%s 注入 SYSTEM_PROMPT"
LOG_SESSION_CONTINUE = "会话续轮 | thread=%s 已有 %d 条历史消息"
LOG_SESSION_COLD_RECOVER = "会话冷启动恢复 | thread=%s messages=%d"
LOG_WINDOW_EXCEEDED = "消息超窗口 | total=%d keeping=%d"

# Tools
LOG_TOOL_SEARCH = "tool:search_wiki | query=%s"
LOG_TOOL_SEARCH_FAILED = "search_wiki失败 | error=%s"
LOG_TOOL_READ = "tool:read_page | path=%s offset=%d max_chars=%d"
LOG_TOOL_READ_UNAUTHORIZED = "read_page 路径越权 | path=%s"
LOG_TOOL_READ_NOT_FOUND = "read_page 文件不存在 | path=%s"
LOG_TOOL_READ_FAILED = "read_page 读取失败 | path=%s error=%s"
LOG_TOOL_READ_SUCCESS = "tool:read_page 成功 | path=%s chars=%d"
LOG_TOOL_GRAPH = "tool:query_graph | question=%s"
LOG_TOOL_GRAPH_FAILED = "query_graph 失败 | error=%s"
