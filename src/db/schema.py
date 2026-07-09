"""
SQLite 数据库建表语句
"""

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    page_type TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    word_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS page_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_path, target_path)
);

CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingest_cache (
    source_path TEXT PRIMARY KEY,
    sha256_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS privacy_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT 'general',
    is_default INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS privacy_categories (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    model TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'unknown',
    input_price REAL NOT NULL,
    output_price REAL NOT NULL,
    cache_hit_price REAL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    source_url TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS graph_relevance (
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    total_score REAL NOT NULL,
    direct_link REAL DEFAULT 0,
    source_overlap REAL DEFAULT 0,
    adamic_adar REAL DEFAULT 0,
    type_affinity REAL DEFAULT 0,
    PRIMARY KEY (source_path, target_path)
);

CREATE TABLE IF NOT EXISTS wiki_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lint_cache (
    cache_key TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingest_queue (
    job_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    context TEXT DEFAULT '{}',
    result_summary TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
