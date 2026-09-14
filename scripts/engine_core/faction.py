"""阵营势差机制：成员战力/影响力评估与宿敌难度的非线性计算。

关键设计：单个"远强"成员的势差要大于三个"相当"成员之和，所以有效值取
``power^2 / 4`` 的平方增长，并对人数施加 15% 的边际衰减，避免堆人数就能
线性堆难度。都市/言情类题材自动切换到"影响力"维度而不是"实力"。
阵营势差为**两大阵营对比**：主角团（主角+伙伴+女主）vs 宿敌团（宿敌+其阵营），
绝不仅看主角一人。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .ripple import difficulty_number

_NONCOMBAT_WORDS = ("都市", "言情", "职场", "social", "romance", "无战斗")
_TEXT_KEYS = ("description", "skill", "background", "role")


@dataclass(frozen=True)
class MemberAssessment:
    name: str
    power: int
    scope: float
    permanence: float
    effective: float
    dimension: str
    background: str = ""


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def infer_power(member: Mapping[str, Any], genre: str = "") -> int:
    """有显式 power/influence 时用显式值；否则从 skill/背景推断 0–4。"""
    if "power" in member or "influence" in member:
        return int(max(0, min(4, round(_number(member.get("power", member.get("influence", 0)))))))
    text = " ".join(str(member.get(key, "")) for key in _TEXT_KEYS)
    blob = (genre + " " + text).lower()
    if any(word in blob for word in ("凡人", "无战斗", "不会武", "普通路人")):
        return 0
    if any(word in blob for word in ("远强", "碾压", "无敌", "毁天", "权倾", "战力拉满")):
        return 4
    if any(word in blob for word in ("高手", "强者", "权势", "世家", "宗主", "掌权")):
        return 3
    if any(word in blob for word in ("相当", "同级", "同伴", "并肩")):
        return 2
    if any(word in blob for word in ("都市", "言情", "职场", "romance", "social")):
        return 0
    return 2 if str(member.get("skill", "")).strip() else 0


def assess_member(member: Mapping[str, Any], genre: str = "") -> MemberAssessment:
    text = " ".join(str(member.get(key, "")) for key in _TEXT_KEYS)
    noncombat = any(word in (genre + text).lower() for word in _NONCOMBAT_WORDS)
    dimension = "影响力" if noncombat else "实力"
    power = infer_power(member, genre)
    scope = max(0.0, min(1.5, _number(member.get("scope", member.get("scope_coefficient", 1)), 1)))
    permanence = max(0.0, min(1.0, _number(member.get("permanence", member.get("residency", 1)), 1)))
    effective = (power * power / 4) * scope * permanence
    return MemberAssessment(str(member.get("name", "成员")), power, scope, permanence,
                            round(effective, 3), dimension,
                            str(member.get("background", "")))


def assess_faction_gap(members: Sequence[Mapping[str, Any] | MemberAssessment],
                       protagonist_power: int = 2, genre: str = "",
                       opposing_members: Sequence[Mapping[str, Any] | MemberAssessment] = ()) -> dict[str, Any]:
    """评估两大阵营的势差（对抗模型）。

    - ``members``：主角团帮手（伙伴/女主；主角本人由 ``protagonist_power``
      给出，同样按 ``power^2/4`` 折算成有效值计入主角团综合）。
    - ``opposing_members``：宿敌方成员（宿敌本人及其阵营）；无信息时按
      "与主角同级"估算。有显式 power/influence 用显式值，否则文本推断。
    - ``delta`` = 宿敌方综合 - 主角团综合；>0 宿敌方更强。
      主角团越豪华（远强伙伴/多女主）→ delta 越小 → 宿敌 D 值越大（相对越弱）；
      宿敌原型越强（反派/远强）→ delta 越大 → D 值越小（越强）。

    单个远强成员（power 4）的势差大于三个相当成员之和（平方增长 + 人数
    边际衰减），都市/言情类自动切到"影响力"维度。
    """
    protagonist_power = max(0, min(4, int(protagonist_power)))
    pp_eff = protagonist_power * protagonist_power / 4.0
    our_cards = [item if isinstance(item, MemberAssessment) else assess_member(item, genre)
                 for item in members[:3]]
    our_side = sum(card.effective for card in our_cards)
    if our_cards:
        our_side /= 1 + 0.15 * (len(our_cards) - 1)
    # 主角团综合 = 主角本人（与帮手同量纲的有效值）+ 帮手阵营（含衰减）
    our_total = pp_eff + our_side
    their_cards = [item if isinstance(item, MemberAssessment) else assess_member(item, genre)
                   for item in (opposing_members or [])[:3]]
    if not their_cards:
        # 无宿敌方信息：宿敌本人按与主角同级估算
        their_cards = [MemberAssessment("宿敌", protagonist_power, 1.0, 1.0, pp_eff,
                                        "影响力" if genre and any(
                                            word in str(genre).lower() for word in _NONCOMBAT_WORDS) else "实力")]
    their_total = sum(card.effective for card in their_cards)
    if their_cards:
        their_total /= 1 + 0.15 * (len(their_cards) - 1)
    delta = their_total - our_total
    bonus = 0 if delta <= 0 else 1 if delta < 1.5 else 2 if delta < 3 else 3
    dimension = our_cards[0].dimension if our_cards else (
        their_cards[0].dimension if their_cards else ("影响力" if genre else "实力"))
    return {"members": our_cards, "opposing_members": their_cards,
            "aggregate": round(our_total, 3), "opposing_aggregate": round(their_total, 3),
            "delta": round(delta, 3),
            "nemesis_bonus": min(3, bonus), "dimension": dimension}


def nemesis_difficulty(player_difficulty: int | float | str = 4,
                       members: Sequence[Mapping[str, Any] | MemberAssessment] = (),
                       protagonist_power: int = 2, genre: str = "",
                       opposing_members: Sequence[Mapping[str, Any] | MemberAssessment] = ()) -> float:
    """计算宿敌强度系数（浮点，0.01–9.99）。

    D 值越小 = 宿敌越强（D0.01 最强，D9.99 最弱）。
    - 基础值由主角难度反向映射：D1→宿敌D9, D9→宿敌D1。
    - 阵营势差 = 宿敌团综合 - 主角团综合（主角团含主角+伙伴+女主）：
      宿敌团越强 → 宿敌 D 值越小（越强），指数衰减让大势差影响更显著。
    - 最终 clamp 到 [0.01, 9.99]。
    """
    pd = difficulty_number(player_difficulty)
    # 基础值：主角越强，宿敌越弱（D 值越大）
    base = 10.0 - pd  # D1→9, D4→6, D9→1
    gap = assess_faction_gap(members, protagonist_power, genre, opposing_members)
    delta = float(gap["delta"])  # 宿敌团综合 - 主角团综合
    # 非线性映射：
    # delta > 0（宿敌更强）→ D 值降低（宿敌变强），用指数衰减让大势差影响更显著
    # delta < 0（宿敌更弱）→ D 值升高（宿敌变弱），用对称的指数增长
    if delta > 0:
        correction = -(3.0 * (1 - math.exp(-delta * 0.8)))
    elif delta < 0:
        correction = 2.0 * (1 - math.exp(delta * 0.8))  # delta<0 → exp<1 → correction>0
    else:
        correction = 0.0
    result = base + correction
    return round(max(0.01, min(9.99, result)), 2)


__all__ = ["MemberAssessment", "infer_power", "assess_member", "assess_faction_gap",
           "nemesis_difficulty"]
