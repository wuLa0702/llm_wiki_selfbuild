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

# 对话摘要压缩：当非 SystemMessage 数量超过此值时触发 summarizer 节点
SUMMARIZE_THRESHOLD = 40
# 摘要后保留的最新对话轮数（1 轮 = user + assistant 共 2 条消息）
SUMMARIZE_KEEP_LATEST_TURNS = 10

# Agent Checkpointer 持久化数据库路径（MemorySaver 纯内存不持久）
# 持久化由 persistence.py 的 SQLite 层负责
PERSISTENCE_DB_PATH = "agent_persistence.db"


# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph 图结构
# ═══════════════════════════════════════════════════════════════════════════════

# 图节点名（必须与 add_node 的第一个参数完全一致）
NODE_AGENT = "agent"
NODE_TOOLS = "tools"
NODE_APPROVE = "approve"
NODE_SUMMARIZER = "summarizer"

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
EVENT_TOOL_APPROVAL_NEEDED = "tool_approval_needed"
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
FIELD_TOOL_CALLS = "tool_calls"
FIELD_APPROVAL = "approval"
FIELD_MESSAGE = "message"
FIELD_EVENT = "event"
FIELD_NAME = "name"
FIELD_DATA = "data"
FIELD_CHUNK = "chunk"
FIELD_RUN_ID = "run_id"

# 工具输出截断长度
TOOL_OUTPUT_DISPLAY_CHARS = 500


# ═══════════════════════════════════════════════════════════════════════════════
# 对话摘要压缩
# ═══════════════════════════════════════════════════════════════════════════════

# 摘要消息前缀（SystemMessage.content 以此开头标记为摘要）
SUMMARIZE_PREFIX = "[对话摘要] "

# 摘要 LLM 系统提示
SUMMARIZE_SYSTEM_PROMPT = """你是对话摘要助手。将以下一段对话历史压缩为一段精炼的中文摘要。

规则：
1. 保留用户询问的核心问题和意图
2. 保留助手回答中的关键知识点、已查询的 Wiki 页面等信息
3. 按时间顺序组织，保持逻辑连贯
4. 如果已存在摘要，将其与新增对话合并生成新的完整摘要
5. 摘要 300 字以内，只输出摘要内容，不要加引导语"""

# 摘要事件类型（SSE 通知前端摘要已执行）
EVENT_SUMMARIZE = "summarize"

# 摘要字段名
FIELD_SUMMARY = "summary"
FIELD_KEY_TOPICS = "key_topics"
FIELD_COMPRESSED_COUNT = "compressed_count"
FIELD_REMAINING_COUNT = "remaining_count"


# ═══════════════════════════════════════════════════════════════════════════════
# 结构化输出
# ═══════════════════════════════════════════════════════════════════════════════

# Agent 响应结构化字段
FIELD_ANSWER = "answer"
FIELD_CITED_PAGES = "cited_pages"
FIELD_FOLLOW_UP_QUESTIONS = "follow_up_questions"


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
ERROR_APPROVAL_REQUIRED = "图已暂停等待审批，但请求未包含审批决策"
ERROR_APPROVAL_FORMAT = "审批决策格式错误，需要 dict"
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
ERROR_SUMMARIZE_FAILED = "对话摘要压缩失败: {}"


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
LOG_APPROVAL_NEEDED = "工具调用等待审批 | thread=%s tools=%s"
LOG_APPROVAL_RESUMED = "工具调用审批结果 | thread=%s decision=%s"

# Summarizer
LOG_SUMMARIZE_SKIP = "摘要压缩跳过 | 消息数=%d 低于阈值=%d"
LOG_SUMMARIZE_START = "摘要压缩开始 | 压缩前 messages=%d (system=%d + conversation=%d)"
LOG_SUMMARIZE_DONE = "摘要压缩完成 | 压缩了 %d 条旧消息, 保留最新 %d 轮, 压缩后 messages=%d"
LOG_SUMMARIZE_FAILED = "摘要压缩失败 | error=%s"

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
