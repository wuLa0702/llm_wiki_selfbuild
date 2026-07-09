"""知识图谱 — WikiGraph + 社区检测 + 洞察"""
from src.core.graph.graph import (NAV_FILES, SIGNAL_WEIGHTS, SOURCES_PATTERN,
                                   WIKILINK_PATTERN, RelevanceSignal, WikiGraph,
                                   parse_frontmatter_sources, parse_wikilinks,
                                   rebuild_graph)
from src.core.graph.community import COHESION_THRESHOLD, CommunityDetector
from src.core.graph.insights import (BRIDGE_COMMUNITY_THRESHOLD,
                                     WEIGHT_CROSS_COMMUNITY,
                                     WEIGHT_CROSS_TYPE, WEIGHT_HUB_SPOKE,
                                     InsightEngine)
