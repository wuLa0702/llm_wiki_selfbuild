import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('docs/agent-architecture-diagrams.md', 'rb') as f:
    raw = f.read()

# Find and show exact bytes around problematic areas
markers = [
    b'else \xe5\x86\xb7\xe5\x90\xaf\xe5\x8a\xa8\xe6\x81\xa2\xe5\xa4\x8d',
    b'save_thread(thread_id',
    b'load_thread(thread_id) \xe2\x86\x92',
    b'subgraph POST /v1/agent/chat/session',
    b'subgraph GET /v1/agent/threads',
]

for marker in markers:
    idx = raw.find(marker)
    if idx >= 0:
        # Find the newline before and after
        start = raw.rfind(b'\n', 0, idx)
        end = raw.find(b'\n', idx)
        line = raw[start+1:end]
        print(f'Marker: {marker[:50]}')
        print(f'  Line: {repr(line)}')
        print()
    else:
        print(f'Marker NOT FOUND: {marker[:50]}')
        print()
