"""桥段库机制：套路加载、九风格确定性分类、触发词检索与模板渲染。

性能取向：``TropeStore`` 首次按触发词检索时惰性预建一次倒排索引，之后的
检索只访问命中的候选而不是全量扫描；``default_store`` 提供进程级缓存，
避免每次调用都重新读盘解析 5 个 JSON。排序键仍是 ``(score, -position)``，
所以结果集与顺序和线性扫描完全一致。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .textkit import split_values as _split_values
from .textkit import tokens as _tokens

STYLE_NAMES = (
    "行动型", "谋略型", "苟稳型", "规则型", "义守型",
    "乐趣型", "探索型", "情感型", "成长型",
)
STYLE_KEYWORDS = {
    "行动型": ("行动", "出手", "战斗", "冒险", "正面", "速度", "冲锋"),
    "谋略型": ("谋略", "布局", "权谋", "算计", "计策", "借力", "谈判"),
    "苟稳型": ("谨慎", "稳健", "保命", "隐忍", "低调", "撤退", "风险"),
    "规则型": ("规则", "机制", "漏洞", "研究", "契约", "逻辑", "推演"),
    "义守型": ("正义", "道义", "守护", "承诺", "责任", "牺牲", "朋友"),
    "乐趣型": ("乐趣", "玩乐", "恶作剧", "随性", "刺激", "混沌", "有趣"),
    "探索型": ("探索", "求知", "未知", "调查", "发现", "远行", "真相"),
    "情感型": ("情感", "羁绊", "陪伴", "信任", "爱", "家人", "共鸣"),
    "成长型": ("成长", "学习", "磨炼", "突破", "自省", "蜕变", "目标"),
}

# 默认桥段库文件，与 data/tropes_manifest.json 的 files 字段保持一致。
DEFAULT_TROPE_FILES = ("tropes_biz.json", "tropes_combat.json", "tropes_life.json",
                       "tropes_mystery.json", "tropes_romance.json")

_TRIGGER_SPLIT_PATTERN = re.compile(r"[,，|、]")


def classify_style(text: Any) -> str:
    """对文本做确定性九风格分类，得分相同取固定声明顺序的风格。"""
    scores = classify_style_scores(text)
    return max(STYLE_NAMES, key=lambda name: (scores[name], -STYLE_NAMES.index(name)))


def classify_style_scores(text: Any) -> dict[str, int]:
    tokens = _tokens(text)
    return {name: sum(1 for keyword in words if keyword in str(text or "").lower() or keyword in tokens)
            for name, words in STYLE_KEYWORDS.items()}


@dataclass(frozen=True)
class Trope:
    id: str
    cat: str = ""
    style: str = ""
    triggers: tuple[str, ...] = ()
    reaction: str = ""
    converge: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: Mapping[str, Any], index: int = 0) -> "Trope":
        def as_text(value: Any) -> str:
            if isinstance(value, (list, tuple, set)):
                return ",".join(str(item) for item in value)
            return "" if value is None else str(value)

        def as_tuple(value: Any) -> tuple[str, ...]:
            if isinstance(value, str):
                return tuple(item.strip() for item in _TRIGGER_SPLIT_PATTERN.split(value) if item.strip())
            if isinstance(value, Iterable):
                return tuple(str(item).strip() for item in value if str(item).strip())
            return ()

        raw = dict(record)
        cat = raw.get("cat", raw.get("category", raw.get("类别", "")))
        style = raw.get("style") or raw.get("styles") or raw.get("风格") or raw.get("choice_styles")
        triggers = raw.get("triggers", raw.get("trigger", raw.get("触发", ())))
        return cls(
            id=as_text(raw.get("id", raw.get("name", f"trope-{index}"))),
            cat=as_text(cat), style=as_text(style), triggers=as_tuple(triggers),
            reaction=as_text(raw.get("reaction", raw.get("反应", ""))),
            converge=as_text(raw.get("converge", raw.get("收束", ""))), data=raw,
        )


class TropeStore:
    """内存套路索引，可由 JSON 数组或 SQLite 表构造。"""

    def __init__(self, tropes: Iterable[Trope] = ()) -> None:
        self.tropes = tuple(tropes)
        self._styles: tuple[frozenset[str], ...] | None = None
        self._trigger_index: dict[str, tuple[int, ...]] | None = None

    @classmethod
    def from_json(cls, path: str | Path) -> "TropeStore":
        target = Path(path)
        if ".." in target.parts:
            raise ValueError("套路数据路径不允许包含 ..")
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping):
            raw = raw.get("tropes", raw.get("items", []))
        if not isinstance(raw, list):
            raise ValueError("套路 JSON 必须是数组或包含 tropes/items 数组的对象")
        return cls(Trope.from_record(item, i) for i, item in enumerate(raw) if isinstance(item, Mapping))

    @classmethod
    def from_sqlite(cls, path: str | Path) -> "TropeStore":
        connection = sqlite3.connect(str(path))
        try:
            data_cursor = connection.cursor()
            rows = data_cursor.execute('SELECT * FROM "tropes"').fetchall()
            data_cursor.close()
            info_cursor = connection.cursor()
            columns = [column[1] for column in info_cursor.execute("SELECT * FROM pragma_table_info(?)", ("tropes",))]
            info_cursor.close()
        finally:
            connection.close()
        return cls(Trope.from_record(dict(zip(columns, row)), i) for i, row in enumerate(rows))

    @classmethod
    def load(cls, path: str | Path, **kwargs: Any) -> "TropeStore":
        suffix = Path(path).suffix.lower()
        if suffix in (".sqlite", ".sqlite3", ".db"):
            return cls.from_sqlite(path, **kwargs)
        return cls.from_json(path)

    def _style_sets(self) -> tuple[frozenset[str], ...]:
        """惰性缓存每条套路的风格集合，避免每次检索重复切分字符串。"""
        if self._styles is None:
            self._styles = tuple(frozenset(_split_values(trope.style)) for trope in self.tropes)
        return self._styles

    def _triggers_index(self) -> dict[str, tuple[int, ...]]:
        """惰性预建触发词到位置的倒排索引，只建一次。"""
        if self._trigger_index is None:
            buckets: dict[str, list[int]] = {}
            for position, trope in enumerate(self.tropes):
                for trigger in set(trope.triggers):
                    buckets.setdefault(trigger, []).append(position)
            self._trigger_index = {key: tuple(value) for key, value in buckets.items()}
        return self._trigger_index

    def _candidates(self, requested: set[str]) -> list[tuple[int, int]]:
        """返回 ``(位置, 触发词命中数)``；无触发词条件时返回全量、命中数 0。"""
        if not requested:
            return [(position, 0) for position in range(len(self.tropes))]
        index = self._triggers_index()
        overlaps: dict[int, int] = {}
        for trigger in requested:
            for position in index.get(trigger, ()):
                overlaps[position] = overlaps.get(position, 0) + 1
        return sorted(overlaps.items())

    def search(self, cat: str | None = None, style: str | None = None,
               triggers: Iterable[str] | str | None = None, limit: int = 20) -> list[Trope]:
        requested = set(_split_values(triggers))
        style_sets = self._style_sets()
        ranked: list[tuple[int, int, Trope]] = []
        for position, overlap in self._candidates(requested):
            trope = self.tropes[position]
            if cat and trope.cat and trope.cat != cat:
                continue
            styles = style_sets[position]
            if style and styles and style not in styles:
                continue
            score = overlap * 10 + (2 if style and style in styles else 0) + (1 if cat and trope.cat == cat else 0)
            ranked.append((score, -position, trope))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:max(0, limit)]]


def load_tropes(path: str | Path, **kwargs: Any) -> TropeStore:
    return TropeStore.load(path, **kwargs)


def search_tropes(store: TropeStore | str | Path, **kwargs: Any) -> list[Trope]:
    if not isinstance(store, TropeStore):
        store = load_tropes(store)
    return store.search(**kwargs)


_STORE_CACHE: dict[tuple[str, ...], TropeStore] = {}
_STORE_LOCK = threading.Lock()


def data_dir() -> Path:
    """桥段库数据目录；PyInstaller 打包后取捆绑目录。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = Path(__file__).resolve().parents[2] / "assets"
    return Path(base) / "data"


def load_store(paths: Iterable[str | Path]) -> TropeStore:
    """按给定路径合并加载并缓存套路库；同一组路径只读盘解析一次。"""
    key = tuple(str(path) for path in paths)
    cached = _STORE_CACHE.get(key)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        cached = _STORE_CACHE.get(key)
        if cached is not None:
            return cached
        tropes: list[Trope] = []
        for path in key:
            if os.path.isfile(path):
                tropes.extend(TropeStore.load(path).tropes)
        store = TropeStore(tropes)
        _STORE_CACHE[key] = store
        return store


def default_store() -> TropeStore:
    """默认桥段库（data/ 下 5 个 JSON 合并），带进程级缓存。"""
    root = data_dir()
    return load_store([root / name for name in DEFAULT_TROPE_FILES])


def clear_store_cache() -> None:
    """清空缓存，便于测试或替换数据源后重新加载。"""
    with _STORE_LOCK:
        _STORE_CACHE.clear()


def instantiate_template(template: str, context: Mapping[str, Any] | None = None) -> str:
    """替换模板中的 {字段}；缺少字段时保留占位符而不抛错。"""
    class _Context(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"
    return str(template or "").format_map(_Context(context or {}))


def render_reaction(template: str, context: Mapping[str, Any] | None = None) -> str:
    return instantiate_template(template, context)


def render_converge(template: str, context: Mapping[str, Any] | None = None) -> str:
    return instantiate_template(template, context)


__all__ = ["STYLE_NAMES", "STYLE_KEYWORDS", "DEFAULT_TROPE_FILES", "classify_style",
           "classify_style_scores", "Trope", "TropeStore", "load_tropes", "search_tropes",
           "data_dir", "load_store", "default_store", "clear_store_cache",
           "instantiate_template", "render_reaction", "render_converge"]
