"""引擎层共用的文本切分工具。

抽出来单独成模块，是为了让 ``ripple``（相容性 K 需要分词）和 ``tropes``
（风格分类需要分词）都不必互相导入，保持机制模块之间零耦合。
"""
from __future__ import annotations

import re
from typing import Any

_SPLIT_PATTERN = re.compile(r"[,，|、]")
_WORD_PATTERN = re.compile(r"[a-z0-9_]+")


def tokens(value: Any) -> set[str]:
    """提取可比较的中英文词；中文按字切分以适配短文本。"""
    text = "" if value is None else str(value).lower()
    words = set(_WORD_PATTERN.findall(text))
    words.update(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    return words


def split_values(value: Any) -> tuple[str, ...]:
    """把逗号/竖线/顿号分隔的字符串或可迭代对象规整为去空白的元组。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in _SPLIT_PATTERN.split(value) if item.strip())
    return tuple(str(item).strip() for item in value if str(item).strip())


__all__ = ["tokens", "split_values"]
