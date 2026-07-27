import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('docs/agent-architecture-diagrams.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Step 1: 🔴 v4 -> 🟡 v4 (current edit shrinks one level)
content = content.replace('🔴 v4', '🟡 v4')
content = content.replace('🔴 v{新版本号}', '🔴 v5')

# Step 2: 🟡 v3 -> 🟢 v3 (only one 🟡 at line 127)
content = content.replace('🟡 v3', '🟢 v3')

# Step 3: 🟢 v# -> remove markers
# Specifically: 🟢 v3 (line 15) and 🟢 v2 (line 16) in the version table
import re
content = re.sub(r' 🟢 v\d+', '', content)

# Step 4: Update version table header
# Line 14 was 🔴 v4 now 🟡 v4 - update its description
content = content.replace(
    '| `🟡 v4` | 最近一次改动的图例 | 对话摘要压缩 summarizer 节点（当前编辑） |',
    '| `🟡 v4` | 最近两次改动的图例 | 对话摘要压缩 summarizer 节点（上一版） |'
)

# 🟢 v2 entry (now marker removed) - update description
content = content.replace(
    '| | 最近三次改动的图例 | 本版本标注规则 |',
    '| | 最近三次改动的图例 | Human-in-the-Loop approve 节点 |'
)

# Add 🔴 v5 entry
content = content.replace(
    '| | 最近三次改动的图例 | Human-in-the-Loop approve 节点 |',
    '| `🔴 v5` | 最近一次改动的图例 | 结构化输出 + 对话摘要压缩 summarizer 节点（当前编辑） |\n| | 最近三次改动的图例 | Human-in-the-Loop approve 节点 |'
)

# Step 5: Update test counts
content = content.replace('测试总数：106', '测试总数：149')

# Update file count references
content = content.replace(
    '├── test_agent.py        ← 44 个测试（含审批测试 + summarizer 路由覆盖）',
    '├── test_agent.py        ← 44 个测试（含审批 + summarizer 路由 + 结构化输出）'
)
content = content.replace(
    '├── test_summarizer.py 🟡 v4 ← 23 个测试（should_summarize/condense_history/边界/降级）',
    '├── test_summarizer.py 🟡 v4 ← 23 个测试（should_summarize/condense_history/边界/降级）'
)

# Fix test count at bottom
content = content.replace(
    'tests/test_api/\n└── test_chat_routes.py  ← 16 个测试（chat + session + threads 端点）',
    'tests/test_agent/\n├── test_qa_approve_summarizer.py 🟡 v4 ← 59 个测试（approve + summarizer QA 集成）\n\n'
    'tests/test_api/\n└── test_chat_routes.py  ← 16 个测试（chat + session + threads 端点）'
)

with open('docs/agent-architecture-diagrams.md', 'w', encoding='utf-8') as f:
    f.write(content)

print('Diagram updated with version rotation and new content')
