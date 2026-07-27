import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('docs/agent-architecture-diagrams.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: else + Route on same line (use 8 spaces)
old1 = 'else 冷启动恢复（MemorySaver 空，SQLite 有数据）        Route->>Persist: load_thread(thread_id) → 持久化历史'
new1 = 'else 冷启动恢复（MemorySaver 空，SQLite 有数据）\n        Route->>Persist: load_thread(thread_id) → 持久化历史'

# Fix 2: subgraph session + direction on same line
old2 = '    subgraph POST /v1/agent/chat/session        direction TB'
new2 = '    subgraph POST /v1/agent/chat/session\n        direction TB'

# Fix 3: subgraph threads + direction on same line
old3 = '    subgraph GET /v1/agent/threads        direction TB'
new3 = '    subgraph GET /v1/agent/threads\n        direction TB'

count = 0
for old, new in [(old1, new1), (old2, new2), (old3, new3)]:
    if old in content:
        content = content.replace(old, new)
        count += 1
        print(f'OK: {old[:40]}...')
    else:
        print(f'NOT FOUND: ...{old[-40:]}')

with open('docs/agent-architecture-diagrams.md', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Fixed {count} issues')
