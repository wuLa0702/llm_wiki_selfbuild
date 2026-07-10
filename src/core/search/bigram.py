"""
CJK Bigram 分词 —— 中文二元分词 + 英文空格分词

为 BM25 搜索提供分词能力：
  - CJK 字符 → 连续滑动 bigram
  - 非 CJK → 空格分词 + 小写化
  - 停用词过滤
  - 支持标题加权
"""
import re

from src.core.search.stopwords import STOPWORDS_ZH

# 中日韩统一表意文字范围
CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")

# 非 CJK 单词（英文/数字）
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*")


def is_cjk(char: str) -> bool:
    """判断单个字符是否为 CJK"""
    return bool(CJK_RE.match(char))


def tokenize(text: str) -> list[str]:
    """
    通用分词：CJK bigram + 英文单词 + 数字

    "机器学习 Python3.12" → ["机器", "器学", "学习", "python3", "3", "12"]
    "自然语言处理(NLP)" → ["自然", "然语", "语言", "言处", "处理", "nlp"]
    """
    if not text:
        return []

    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if is_cjk(ch):
            # 收集连续的 CJK 字符
            start = i
            while i < len(text) and is_cjk(text[i]):
                i += 1
            cjk_seq = text[start:i]
            # 生成 bigram
            tokens.extend(_cjk_bigram(cjk_seq))
        elif ch.isalnum() or ch in "-_":
            # 收集连续的字母数字
            start = i
            while i < len(text) and (text[i].isalnum() or text[i] in "-_"):
                i += 1
            word = text[start:i].lower()
            tokens.append(word)
        else:
            i += 1

    # 过滤停用词和单字符（数字/字母单字符保留，CJK 单字符过滤）
    filtered = []
    for t in tokens:
        if len(t) <= 1 and is_cjk(t[0]) if t else False:
            continue  # 过滤 CJK 单字符
        if t in STOPWORDS_ZH:
            continue
        filtered.append(t)

    return filtered


def _cjk_bigram(seq: str) -> list[str]:
    """生成 CJK 连续序列的 bigram

    >>> _cjk_bigram("机器学习")
    ["机器", "器学", "学习"]
    >>> _cjk_bigram("人工智能")
    ["人工", "工智", "智能"]
    >>> _cjk_bigram("A")  # 非 CJK
    []
    """
    if len(seq) < 2:
        return [seq] if seq else []
    return [seq[i:i + 2] for i in range(len(seq) - 1)]


def build_searchable_tokens(text: str, title: str = "") -> list[str]:
    """
    构建可搜索的分词结果（标题加权）

    Args:
        text: 页面正文
        title: 页面标题（在结果中重复出现 3 次以提高权重）

    Returns:
        分词 token 列表（含重复，供 BM25 词频统计）
    """
    tokens = []
    if title:
        # 标题重复 3 次提高权重
        tokens.extend(tokenize(title) * 3)
    tokens.extend(tokenize(text))
    return tokens
