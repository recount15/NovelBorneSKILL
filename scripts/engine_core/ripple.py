"""涟漪机制：影响等级 L0–L4、积势账目、收束相容性 K 与难度解析。

纯计算、无 IO、无外部依赖，因此完全可离线复现：同样的输入必然得到同样的
等级与判定。改世不是靠模型自由裁量，而是靠"积势是否达标 + 剧情是否到后期"
两个可验证条件。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from .textkit import tokens as _tokens

_DIGIT_PATTERN = re.compile(r"[1-9]")


def difficulty_number(value: int | float | str) -> int:
    """从任意难度表述里取出 1–9 的编号（支持小数如 6.35→6），取不到时按普通难度 4 处理。"""
    match = _DIGIT_PATTERN.search(str(value))
    return max(1, min(9, int(match.group()) if match else 4))


# 收束力对积势门槛的倍率：与产品三档词汇对齐（participation.CONVERGENCE_LEVELS）。
# 一般收束世界惯性小（攒势快），极高收束惯性大（攒势慢）。
CONVERGENCE_MULT: dict[str, float] = {"一般": 0.75, "较高": 1.0, "极高": 1.4}


def normalize_convergence(value: Any) -> str:
    """收束力档位归一：只认 一般/较高/极高（与动态收束系统同词表），其余较高。"""
    text = str(value or "").strip()
    for tier in CONVERGENCE_MULT:
        if tier in text:
            return tier
    return "较高"


def ripple_threshold(difficulty: int | str = 4, convergence: Any = None) -> int:
    """积势门槛：难度（6–8 基础）× 收束力倍率（一般 0.75 / 较高 1.0 / 极高 1.4）。

    三档收束力在真人实测中形成可感知差异：一般收束 5–6 点即可 ready，
    较高 6–8 点，极高 8–11 点——同样的大动作节奏下，高收束世界要多铺几轮。
    """
    base = min(8, 6 + (difficulty_number(difficulty) - 1) // 4)
    mult = CONVERGENCE_MULT.get(normalize_convergence(convergence), 1.0)
    return max(3, min(12, int(round(base * mult))))


def compatibility_k(action: Any, anchor: Any = "", style: str | None = None,
                    trigger_overlap: int = 0) -> int:
    """计算行动与锚点的相容性 K（0–100），K>=60 表示可共存。"""
    left, right = _tokens(action), _tokens(anchor)
    overlap = len(left & right) / max(1, len(left | right))
    contains_anchor = bool(right) and right.issubset(left)
    base = round(overlap * 70 + (25 if contains_anchor else 0) + min(20, max(0, trigger_overlap) * 5))
    if style and style in str(anchor):
        base += 10
    return max(0, min(100, base))


k_value = compatibility_k


class ImpactLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


@dataclass(frozen=True)
class RippleAssessment:
    raw_level: ImpactLevel
    effective_level: ImpactLevel
    score: float
    pressure: int
    threshold: int
    allowed: bool
    progress: float
    reason: str

    @property
    def level(self) -> ImpactLevel:
        """兼容旧调用；运行时展示使用当前有效等级。"""
        return self.effective_level


@dataclass(frozen=True)
class RippleEntry:
    step: int
    raw_level: ImpactLevel
    effective_level: ImpactLevel
    pressure: int
    attempt_total: int
    effective_total: int
    threshold: int
    progress: float
    allowed: bool
    note: str = ""

    @property
    def level(self) -> ImpactLevel:
        return self.effective_level

    @property
    def total(self) -> int:
        """兼容旧存档和 UI；total 始终表示可用于门禁的有效积势。"""
        return self.effective_total


def _unit_score(value: float | int) -> float:
    number = float(value or 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0.0, min(1.0, number / 4))
    return max(0.0, min(1.0, number / 4 if number > 1 else number))


def impact_level(breadth: float = 0, persistence: float = 0,
                 canon_conflict: float = 0, progress: float = 0) -> ImpactLevel:
    score = (_unit_score(breadth) * 3 + _unit_score(persistence) * 3 +
             _unit_score(canon_conflict) * 4)
    level = ImpactLevel(min(4, int(score // 2.0)))
    if level == ImpactLevel.L4 and float(progress) <= 0.6:
        return ImpactLevel.L3
    return level


def assess_ripple(breadth: float = 0, persistence: float = 0,
                  canon_conflict: float = 0, *, progress: float = 0,
                  difficulty: int | str = 4, pressure: int | None = None,
                  current_total: int = 0, convergence: Any = None) -> RippleAssessment:
    score = (_unit_score(breadth) * 3 + _unit_score(persistence) * 3 +
             _unit_score(canon_conflict) * 4)
    raw_level = ImpactLevel(min(4, int(score // 2.0)))
    level = raw_level if raw_level != ImpactLevel.L4 or float(progress) > 0.6 else ImpactLevel.L3
    value = max(0, min(3, int(pressure if pressure is not None else round(score / 4))))
    threshold = ripple_threshold(difficulty, convergence)
    projected = int(current_total) + value
    allowed = raw_level <= ImpactLevel.L2 or (
        projected >= threshold
        and (raw_level < ImpactLevel.L4 or float(progress) > 0.6)
    )
    reason = "原著锚点优先保留" if level <= ImpactLevel.L2 else ("积势达标，可评估改变路径" if allowed else "L3/L4需累计积势，L4还需剧情后期")
    return RippleAssessment(
        raw_level=raw_level,
        effective_level=level,
        score=round(score, 3),
        pressure=value,
        threshold=threshold,
        allowed=allowed,
        progress=max(0.0, min(1.0, float(progress))),
        reason=reason,
    )


class RippleLedger:
    """透明涟漪账目：每次行动保留影响、积势、门槛和判定。"""

    def __init__(self, difficulty: int | str = 4, convergence: Any = None) -> None:
        self.difficulty = difficulty_number(difficulty)
        self.convergence = normalize_convergence(convergence)
        self.attempt_total = 0
        self.effective_total = 0
        self.entries: list[RippleEntry] = []

    @property
    def total(self) -> int:
        """兼容旧调用；门禁只读取有效积势。"""
        return self.effective_total

    @total.setter
    def total(self, value: int) -> None:
        self.effective_total = max(0, int(value or 0))

    @property
    def threshold(self) -> int:
        return ripple_threshold(self.difficulty, self.convergence)

    def add(self, breadth: float = 0, persistence: float = 0,
            canon_conflict: float = 0, progress: float = 0,
            pressure: int | None = None, note: str = "") -> RippleEntry:
        assessment = assess_ripple(breadth, persistence, canon_conflict,
                                   progress=progress, difficulty=self.difficulty,
                                   pressure=pressure, current_total=self.effective_total,
                                   convergence=self.convergence)
        self.attempt_total += assessment.pressure
        if assessment.allowed:
            self.effective_total += assessment.pressure
        entry = RippleEntry(
            step=len(self.entries) + 1,
            raw_level=assessment.raw_level,
            effective_level=assessment.effective_level,
            pressure=assessment.pressure,
            attempt_total=self.attempt_total,
            effective_total=self.effective_total,
            threshold=assessment.threshold,
            progress=assessment.progress,
            allowed=assessment.allowed,
            note=note,
        )
        self.entries.append(entry)
        return entry

    def transparent(self) -> list[dict[str, Any]]:
        return [{
            "step": e.step,
            "raw_level": e.raw_level.name,
            "effective_level": e.effective_level.name,
            "level": e.level.name,
            "pressure": e.pressure,
            "attempt_total": e.attempt_total,
            "effective_total": e.effective_total,
            "total": e.total,
            "threshold": e.threshold,
            "progress": e.progress,
            "allowed": e.allowed,
            "note": e.note,
        } for e in self.entries]


def anchor_outcome(anchor: str, action: str = "", k: int | None = None) -> dict[str, Any]:
    """原著锚点必发生；行动只改变路径。K不足时自动采用保守共存表述。"""
    value = compatibility_k(action, anchor) if k is None else max(0, min(100, int(k)))
    return {"anchor": anchor, "must_happen": True, "k": value,
            "outcome": "锚点以兼容路径发生" if value >= 60 else "锚点按原有因果发生，行动转化为旁支"}


__all__ = ["ImpactLevel", "RippleAssessment", "RippleEntry", "RippleLedger",
           "difficulty_number", "ripple_threshold", "impact_level", "assess_ripple",
           "compatibility_k", "k_value", "anchor_outcome"]
