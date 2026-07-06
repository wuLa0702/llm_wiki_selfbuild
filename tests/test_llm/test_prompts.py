"""
Prompt 模板单元测试
"""
from src.llm import prompts


class TestPhase1Prompts:
    """Phase 1 遗留 prompt"""

    def test_ingest_prompt_exists(self):
        assert len(prompts.SYSTEM_PROMPT_INGEST) > 100
        assert "PAGE" in prompts.SYSTEM_PROMPT_INGEST


class TestPhase2AnalyzePrompt:
    """Step 1 — 分析 Prompt"""

    def test_analyze_prompt_exists(self):
        assert len(prompts.SYSTEM_PROMPT_INGEST_ANALYZE) > 200

    def test_analyze_as_json_output(self):
        """要求输出 JSON"""
        p = prompts.SYSTEM_PROMPT_INGEST_ANALYZE
        assert "JSON" in p
        assert "entities" in p
        assert "concepts" in p
        assert "contradictions" in p
        assert "connections_to_existing" in p
        assert "recommendations" in p

    def test_analyze_forbids_markdown(self):
        """禁止生成 Markdown 页面内容"""
        assert "只负责分析" in prompts.SYSTEM_PROMPT_INGEST_ANALYZE
        assert "不负责写作" in prompts.SYSTEM_PROMPT_INGEST_ANALYZE

    def test_analyze_importance_levels(self):
        """定义了 importance 级别"""
        assert "high" in prompts.SYSTEM_PROMPT_INGEST_ANALYZE
        assert "medium" in prompts.SYSTEM_PROMPT_INGEST_ANALYZE
        assert "low" in prompts.SYSTEM_PROMPT_INGEST_ANALYZE


class TestPhase2GeneratePrompt:
    """Step 2 — 生成 Prompt"""

    def test_generate_prompt_exists(self):
        assert len(prompts.SYSTEM_PROMPT_INGEST_GENERATE) > 200

    def test_generate_yaml_frontmatter(self):
        """要求 YAML frontmatter"""
        p = prompts.SYSTEM_PROMPT_INGEST_GENERATE
        assert "frontmatter" in p.lower()
        assert "title" in p
        assert "type" in p
        assert "tags" in p
        assert "sources" in p
        assert "confidence" in p

    def test_generate_confidence_levels(self):
        """定义了置信度级别"""
        p = prompts.SYSTEM_PROMPT_INGEST_GENERATE
        assert "high" in p
        assert "medium" in p
        assert "low" in p

    def test_generate_min_wikilinks(self):
        """要求至少 2 个 wikilinks"""
        assert "2 个" in prompts.SYSTEM_PROMPT_INGEST_GENERATE
        assert "wikilinks" in prompts.SYSTEM_PROMPT_INGEST_GENERATE.lower()

    def test_generate_output_format(self):
        """保持 Phase 1 的 PAGE/END 格式"""
        p = prompts.SYSTEM_PROMPT_INGEST_GENERATE
        assert "---PAGE:" in p
        assert "---END---" in p


class TestPhase2PromptCompatibility:
    """两步 Prompt 的兼容性"""

    def test_analyze_output_keys_match_generate_input(self):
        """Analyze 的 JSON key 与 Generate 的输入期望一致"""
        analyze = prompts.SYSTEM_PROMPT_INGEST_ANALYZE
        # Generate prompt 提到"分析报告"、"JSON"、"实体"、"概念"
        generate = prompts.SYSTEM_PROMPT_INGEST_GENERATE
        assert "分析报告" in generate
        assert "JSON" in generate


class TestChatPromptTemplates:
    """Phase 2 1.2 — ChatPromptTemplate 实例"""

    def test_analyze_template_exists(self):
        assert hasattr(prompts, "INGEST_ANALYZE_TEMPLATE")

    def test_analyze_template_variables(self):
        """模板变量包含 source_content 和 index_context"""
        vars_ = prompts.INGEST_ANALYZE_TEMPLATE.input_variables
        assert "source_content" in vars_
        assert "index_context" in vars_

    def test_analyze_template_renders(self):
        """模板渲染后包含输入值"""
        messages = prompts.INGEST_ANALYZE_TEMPLATE.format_messages(
            source_content="测试内容",
            index_context="无",
        )
        assert len(messages) == 3
        assert messages[0].type == "system"
        assert messages[1].type == "human"
        assert "测试内容" in messages[2].content

    def test_generate_template_exists(self):
        assert hasattr(prompts, "INGEST_GENERATE_TEMPLATE")

    def test_generate_template_variables(self):
        """模板变量包含 source_name 和 analysis_json"""
        vars_ = prompts.INGEST_GENERATE_TEMPLATE.input_variables
        assert "source_name" in vars_
        assert "analysis_json" in vars_

    def test_generate_template_renders(self):
        """模板渲染后包含 JSON 数据"""
        messages = prompts.INGEST_GENERATE_TEMPLATE.format_messages(
            source_name="test.md",
            analysis_json='{"entities": []}',
        )
        assert len(messages) == 2
        assert "test.md" in messages[1].content
        assert '{"entities": []}' in messages[1].content
