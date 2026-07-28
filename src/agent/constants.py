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

# Summarizer LLM 配置（单独的小模型实例）
ENV_SUMMARIZER_MODEL = "SUMMARIZER_MODEL"
ENV_SUMMARIZER_API_KEY = "SUMMARIZER_API_KEY"
ENV_SUMMARIZER_API_BASE = "SUMMARIZER_API_BASE"
ENV_SUMMARIZER_TIMEOUT = "SUMMARIZER_TIMEOUT"
ENV_SUMMARIZER_MAX_RETRIES = "SUMMARIZER_MAX_RETRIES"

# 固定 DeepSeek v4 Flash 作为摘要压缩专用模型
DEFAULT_SUMMARIZER_MODEL = "deepseek-v4-flash"
# 未单独配置时，复用主 LLM 的 API Key 和 Base URL
# timeout 略高于主模型（摘要需处理更多文本）
DEFAULT_SUMMARIZER_TIMEOUT = 30
DEFAULT_SUMMARIZER_MAX_RETRIES = 2


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
# 工作记忆（Working Memory）
# ═══════════════════════════════════════════════════════════════════════════════

# 状态键
STATE_WORKING_MEMORY = "working_memory"

# 工作记忆槽位名
WM_SLOT_USER_IDENTITY = "user_identity"
WM_SLOT_CURRENT_GOAL = "current_goal"
WM_SLOT_KEY_FACTS = "key_facts"
WM_SLOT_TOOL_CACHE = "tool_cache"
WM_SLOT_ENTITIES = "entities_mentioned"

# 槽优先级（内置槽位隐式优先级: goal=3, identity=3, facts=2, entities=1, cache=1）
WM_SLOT_CRITICAL = {WM_SLOT_CURRENT_GOAL, WM_SLOT_USER_IDENTITY}  # 永不降级
WM_SLOT_HIGH = {WM_SLOT_KEY_FACTS}
WM_SLOT_MEDIUM = {WM_SLOT_ENTITIES}
WM_SLOT_LOW = {WM_SLOT_TOOL_CACHE}

# 槽大小上限
WM_MAX_FACTS = 20
WM_MAX_ENTITIES = 50
WM_MAX_TOOL_CACHE_ENTRIES = 5

# 图节点
NODE_EXTRACT_WM = "extract_wm"
NODE_WM_EVICTION = "wm_eviction"


# ═══════════════════════════════════════════════════════════════════════════════
# 索引表
# ═══════════════════════════════════════════════════════════════════════════════

# 实体索引：消息中出现 ≥ N 次的词/短语自动纳入索引
THREAD_ENTITY_MIN_FREQ = 2

# 搜索默认值
SEARCH_CONVERSATIONS_LIMIT = 20
GLOBAL_ENTITIES_LIMIT = 50


# ═══════════════════════════════════════════════════════════════════════════════
# Attention Sink（关键信息锚定）
# ═══════════════════════════════════════════════════════════════════════════════

# AgentState 中 attention_sinks 字段名
STATE_ATTENTION_SINKS = "attention_sinks"

# 检测模式：用户消息中含以下关键词时触发自动锚定
SINK_PATTERNS = (
    # 显式记忆指令
    "记住", "请记住", "别忘记", "不要忘记", "牢记",
    # 自我介绍
    "我叫", "我的名字", "我是", "我是一名",
    # 偏好和习惯
    "我喜欢", "我不喜欢", "我习惯", "我想要", "我希望",
    # 重要上下文
    "重要的是", "关键是", "请注意", "注意", "务必",
    "我的项目", "我目前", "我正在",
    # 事实性信息
    "我的邮箱", "我的电话", "我住在", "我的公司",
    "我的团队", "我负责",
)

# Attention Sink 常量
ATTENTION_SINK_MAX = 15                # 最多保留多少个锚定
ATTENTION_SINK_MIN_CONFIDENCE = 0.3    # 置信度低于此值自动清理
SINK_CONFIDENCE_NEW = 0.8              # 新检测到的锚定初始置信度
SINK_CONFIDENCE_REINFORCE = 0.9        # 被再次提及时重置的置信度
SINK_DECAY_PER_TURN = 0.05             # 每轮衰减量
SINK_REINFORCE_TURNS = 5               # 多少轮未强化则开始衰减
SINK_PATTERN_MIN_LENGTH = 2            # 模式匹配后内容至少2个字
FREQUENCY_SINK_THRESHOLD = 3           # 实体出现≥N次自动锚定
SINK_CONTENT_MAX_CHARS = 200           # 单条锚定内容最大长度

# 置信度持续低于阈值的轮数上限，超出则移出
SINK_MAX_IDLE_TURNS = 20

# 锚定信息注入 LLM 的 SystemMessage 模板
SINK_SYSTEM_PROMPT = """以下是对话中用户明确要求记住或反复提及的重要信息（每条包含置信度）：

{sink_lines}

请在日常回答中参考这些信息。如果问题与这些信息无关，忽略即可。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 记忆降级归档 — Memory Degradation
# ═══════════════════════════════════════════════════════════════════════════════

# 默认归档天数：会话最后更新超过此天数后进入"已归档"状态
ARCHIVE_DAYS = 30

# 归档后消息的前缀标记（与 SUMMARIZE_PREFIX 区分，表示完整对话归档）
ARCHIVE_PREFIX = "[归档摘要] "

# 恢复归档会话时的提示 SystemMessage 模板
ARCHIVE_RESTORE_NOTICE = (
    "注意：以下对话是从归档状态恢复的。"
    "之前的内容已被压缩为摘要，你可能需要重新提供更具体的上下文。\n\n"
    "【对话摘要】\n{summary}\n\n"
    "请继续提问，我会在已有上下文的基础上回答。"
)

# 日志模板
LOG_ARCHIVE_START = "会话归档检查 | thread=%s 已闲置 %.1f 天"
LOG_ARCHIVE_DONE = "会话归档完成 | thread=%s 压缩前=%d 条 → 摘要后=%d 条"
LOG_ARCHIVE_SKIP = "会话归档跳过 | thread=%s 原因=%s"
LOG_ARCHIVE_ERROR = "会话归档失败 | thread=%s error=%s"

# 归档系统提示（复用对话摘要的 prompt 结构，但说明是完整对话归档）
ARCHIVE_SYSTEM_PROMPT = """你是对话归档助手。将以下一段完整对话压缩为一段精炼的中文摘要。

规则：
1. 保留用户询问的核心问题、意图和已解决的问题
2. 保留助手回答中的关键知识点和结论
3. 保留对话中出现的 Wiki 页面引用、工具调用结果等上下文
4. 按时间顺序组织，保持逻辑连贯
5. 摘要 300 字以内，只输出摘要内容，不要加引导语
6. 这是归档摘要，将永久替代原始对话——请确保不遗漏重要信息"""


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 消息角色
# ═══════════════════════════════════════════════════════════════════════════════
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
