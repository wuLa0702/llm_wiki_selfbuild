import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('docs/agent-architecture-diagrams.md', 'r', encoding='utf-8') as f:
    content = f.read()

# All the fixes - find exact text matches
import re

# Fix 1: else block line 77
old1 = 'else 冷启动恢复（MemorySaver 空，SQLite 有数据）\t\tRoute->>Persist: load_thread(thread_id) → 持久化历史'
new1 = 'else 冷启动恢复（MemorySaver 空，SQLite 有数据）\n\t\tRoute->>Persist: load_thread(thread_id) → 持久化历史'

# Fix 2: save_thread line 284
old2 = 'Route->>Persist: save_thread("t1", [...])\tRoute-->>Client: done'
new2 = 'Route->>Persist: save_thread("t1", [...])\n\tRoute-->>Client: done'

# Fix 3: load_thread line 291
old3 = 'Route->>Persist: load_thread("t1") → 返回持久化历史\tRoute->>Graph: astream_events({messages: [历史 + Human("继续")]})'
new3 = 'Route->>Persist: load_thread("t1") → 返回持久化历史\n\tRoute->>Graph: astream_events({messages: [历史 + Human("继续")]})'

# Fix 4: save_thread line 293 (same pattern as 2)
old4 = 'Route->>Persist: save_thread("t1", [...])\tRoute-->>Client: done'
new4 = 'Route->>Persist: save_thread("t1", [...])\n\tRoute-->>Client: done'

# Fix 5: load_thread line 300
old5 = 'Route->>Persist: load_thread("t2") → None\tRoute->>Graph: astream_events({messages: [System, Human("新问题")]})'
new5 = 'Route->>Persist: load_thread("t2") → None\n\tRoute->>Graph: astream_events({messages: [System, Human("新问题")]})'

# Fix 6: save_thread line 302
old6 = 'Route->>Persist: save_thread("t2", [...])\tRoute-->>Client: done'
new6 = 'Route->>Persist: save_thread("t2", [...])\n\tRoute-->>Client: done'

# Fix 7: subgraph direction line 319
old7 = 'subgraph POST /v1/agent/chat/session\t\tdirection TB'
new7 = 'subgraph POST /v1/agent/chat/session\n\t\tdirection TB'

# Fix 8: subgraph direction line 326
old8 = 'subgraph GET /v1/agent/threads\t\tdirection TB'
new8 = 'subgraph GET /v1/agent/threads\n\t\tdirection TB'

pairs = [(old1, new1), (old2, new2), (old3, new3), (old4, new4), (old5, new5), (old6, new6), (old7, new7), (old8, new8)]

count = 0
for i, (old, new) in enumerate(pairs, 1):
    if old in content:
        content = content.replace(old, new)
        count += 1
        print(f'Fix {i}: OK')
    else:
        print(f'Fix {i}: NOT FOUND - trying hex search...')
        # Print the first differing bytes
        idx = content.find(old[:20])
        if idx >= 0:
            print(f'  Found prefix at {idx}, context: {repr(content[idx:idx+50])}')
        else:
            # Try to find by deducing the tab/space issue
            lines = content.split('\n')
            for li, line in enumerate(lines):
                if 'save_thread' in line and 'Route-->>' in line and li >= 280:
                    print(f'  Line {li+1}: {repr(line[:100])}')

with open('docs/agent-architecture-diagrams.md', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Fixed {count}/{len(pairs)} issues')
