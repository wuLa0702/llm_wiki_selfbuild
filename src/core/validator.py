"""
Wiki 页面内容校验器 — 校验路径、Frontmatter、脚本注入、链接
"""
import re


class ValidatorError(Exception):
    """校验失败异常"""


class WikiValidator:
    """Wiki 页面内容校验器"""

    VALID_TYPES = {"entity", "concept", "source", "query", "synthesis"}
    FORBIDDEN_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
        r"javascript:",
        r"onclick\s*=",
        r"onload\s*=",
    ]

    @staticmethod
    def validate_path(path: str) -> None:
        """
        校验页面路径

        允许规则：
          - 根目录文件: index.md, log.md, overview.md
          - 子目录文件: entities/xxx.md, concepts/xxx.md, sources/xxx.md, queries/xxx.md

        Raises:
            ValidatorError: 路径为空、含 ../、不在允许目录下
        """
        if not path or not path.strip():
            raise ValidatorError("Path must not be empty")

        if ".." in path:
            raise ValidatorError(f"Path must not contain '..': {path}")

        root_files = {"index.md", "log.md", "overview.md", "purpose.md"}
        if path in root_files:
            if not path.endswith(".md"):
                raise ValidatorError(f"Path must end with .md: {path}")
            return

        allowed_prefixes = ("entities/", "concepts/", "sources/", "queries/")
        if not any(path.startswith(p) for p in allowed_prefixes):
            raise ValidatorError(
                f"Path must be under entities/ concepts/ sources/ or queries/: {path}"
            )

        if not path.endswith(".md"):
            raise ValidatorError(f"Path must end with .md: {path}")

    @staticmethod
    def validate_frontmatter(content: str) -> dict:
        """
        校验 YAML frontmatter

        Args:
            content: 页面完整内容

        Returns:
            解析后的 frontmatter dict

        Raises:
            ValidatorError: frontmatter 格式错误、缺少 title 或 type
        """
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            raise ValidatorError("Missing YAML frontmatter")

        raw = match.group(1)
        fm: dict[str, object] = {}

        for line in raw.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Parse YAML-ish values (simple cases)
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                fm[key] = [i.strip().strip('"\'') for i in items if i.strip()]
            else:
                fm[key] = value.strip('"\' ')

        if "title" not in fm or not fm["title"]:
            raise ValidatorError("Frontmatter must contain 'title'")

        if "type" not in fm or not fm["type"]:
            raise ValidatorError("Frontmatter must contain 'type'")

        if fm["type"] not in WikiValidator.VALID_TYPES:
            raise ValidatorError(
                f"Invalid type '{fm['type']}'. "
                f"Must be one of: {', '.join(sorted(WikiValidator.VALID_TYPES))}"
            )

        return fm

    @staticmethod
    def validate_no_executable(content: str) -> None:
        """
        禁止可执行内容注入

        Raises:
            ValidatorError: 发现 <script>/<iframe>/javascript: 等
        """
        for pattern in WikiValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                raise ValidatorError(
                    f"Content contains forbidden pattern: {pattern}"
                )

    @staticmethod
    def validate_wikilinks(content: str) -> list[str]:
        """
        检查页面包含至少 1 个 wikilink

        Returns:
            wikilink 路径列表

        Raises:
            ValidatorError: 没有 wikilink
        """
        links = re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]", content)
        if not links:
            raise ValidatorError("Content must contain at least 1 [[wikilink]]")
        return [l.strip() for l in links]

    @staticmethod
    def validate_all(path: str, content: str) -> dict:
        """
        执行全部校验

        Returns:
            frontmatter dict

        Raises:
            ValidatorError: 任意校验失败
        """
        WikiValidator.validate_path(path)
        WikiValidator.validate_no_executable(content)
        fm = WikiValidator.validate_frontmatter(content)
        WikiValidator.validate_wikilinks(content)
        return fm
