"""动态收束力：把「一般/较高/极高」三档收束力改造成连续位置 + 有界漂移的纯代码机制。

设计论证（实现严格照此）：

- 连续位置 position ∈ [0,1]，三档为区间：一般 [0,0.25)，较高 [0.25,0.75]，
  极高 (0.75,1]。0.25 是降档刻度、0.75 是升档刻度；起始位置取区间中点
  （一般 0.125、较高 0.5、极高 0.875），让换挡需要「走完半个区间」，
  天然形成区间滞回（zone hysteresis）。
- 有界漂移 + 滞回：单步幅度 clamp(0.02*weight, 0.005, 0.05)，即使 weight 拉满
  每回合最多移动 0.05，从区间中点跨过半个区间（0.375）至少需要 8 个满重回合，
  保证「长期行为才换挡、单回合不剧烈抖动」；即使连续向同一方向结算，也强制
  「单回合最多越过一个区间边界」，杜绝一次结算连跳两档。
- 回归项：none（本回合无锚点结算）时向 base 起始位置回归，幅度为漂移量的一半。
  没有回归项时，一旦某类 outcome 长期缺席，position 会无限单向漂移并锁死在
  端点；半速回归让「无事件发生」的回合缓慢稀释极端偏移，同时不会盖过真实
  结算带来的趋势（回归速度只有漂移速度的一半）。
- 非对称 clamp：base=极高 时 position 下限 0.25（永远降不到一般区），base=一般
  时上限 0.75（永远升不到极高区），base=较高 全区间自由。高档收束力世界不应
  因为玩家几回合的偏移就彻底放开锚点，低档世界也不应被永久锁死到原封不动——
  极端档位只能向中间靠拢，不能跳到另一个极端。

本模块纯计算、无 IO、不调用模型；同样输入序列必然得到同样的位置轨迹。
"""
from __future__ import annotations

from typing import Any, Mapping

TIERS = ("一般", "较高", "极高")
DOWN_THRESHOLD = 0.25
UP_THRESHOLD = 0.75
START_POSITIONS = {"一般": 0.125, "较高": 0.5, "极高": 0.875}
OUTCOMES = ("faithful", "offset", "reversed", "none")
HISTORY_LIMIT = 20

_STEP_BASE = 0.02
_STEP_MIN = 0.005
_STEP_MAX = 0.05
_REVERSED_FACTOR = 1.5
_REGRESSION_FACTOR = 0.5


def _normalize_base(base_tier: Any) -> str:
    text = str(base_tier or "").strip()
    if text not in TIERS:
        raise ValueError(f"未知收束力档位: {base_tier!r}（可选 {list(TIERS)}）")
    return text


def _tier_of(position: float) -> str:
    if position < DOWN_THRESHOLD:
        return "一般"
    if position <= UP_THRESHOLD:
        return "较高"
    return "极高"


def _allowed_bounds(base: str) -> tuple[float, float]:
    """base 档位的允许区间：极端档位不能跳到另一个极端。"""
    if base == "极高":
        return (DOWN_THRESHOLD, 1.0)
    if base == "一般":
        return (0.0, UP_THRESHOLD)
    return (0.0, 1.0)


def init_state(base_tier: str) -> dict[str, Any]:
    """按 base 档位初始化动态收束力状态。"""
    base = _normalize_base(base_tier)
    position = START_POSITIONS[base]
    return {
        "base": base,
        "position": position,
        "effective": base,
        "last_settled_position": position,
        "history": [],
    }


def settle(conv: dict[str, Any], outcome: str, weight: float = 1.0,
           round: int | None = None) -> dict[str, Any]:
    """按本回合锚点结算结果推动收束力位置，返回更新后的 conv（原地修改）。

    outcome ∈ {"faithful","offset","reversed","none"}：
    - faithful（锚点原样履约）      -> 左移（向一般漂移）
    - offset（以积势偏移形式履约）  -> 右移
    - reversed（锚点被完全扭转）    -> 右移，幅度 ×1.5
    - none（本回合无锚点结算）      -> 向 base 起始位置半速回归
    """
    if not isinstance(conv, dict):
        raise ValueError("conv 必须是 init_state 返回的状态字典")
    base = _normalize_base(conv.get("base"))
    outcome = str(outcome or "").strip()
    if outcome not in OUTCOMES:
        raise ValueError(f"未知结算结果: {outcome!r}（可选 {list(OUTCOMES)}）")
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        weight = 1.0
    step = max(_STEP_MIN, min(_STEP_MAX, _STEP_BASE * weight))

    old_position = max(0.0, min(1.0, float(conv.get("position", START_POSITIONS[base]))))
    start = START_POSITIONS[base]

    if outcome == "faithful":
        position = old_position - step
    elif outcome == "offset":
        position = old_position + step
    elif outcome == "reversed":
        position = old_position + step * _REVERSED_FACTOR
    else:  # none：向 base 起始位置回归，幅度为漂移量的一半
        gap = start - old_position
        move = min(step * _REGRESSION_FACTOR, abs(gap))
        position = old_position + (move if gap > 0 else -move)

    position = max(0.0, min(1.0, position))

    # 单回合最多越过一个区间边界：跨过两个边界时钳制到相邻边界，
    # 保证任何单次结算都不会连跳两档。
    old_index = TIERS.index(_tier_of(old_position))
    new_index = TIERS.index(_tier_of(position))
    if new_index - old_index >= 2:
        position = UP_THRESHOLD
    elif old_index - new_index >= 2:
        position = DOWN_THRESHOLD

    # 非对称 clamp：极高永不降入一般区，一般永不升入极高区。
    lo, hi = _allowed_bounds(base)
    position = max(lo, min(hi, position))

    conv["base"] = base
    conv["last_settled_position"] = old_position
    conv["position"] = position
    conv["effective"] = _tier_of(position)
    entry: dict[str, Any] = {"outcome": outcome, "position": position, "effective": conv["effective"]}
    if round is not None:
        entry["round"] = int(round)
    history = conv.get("history")
    history = list(history) if isinstance(history, list) else []
    history.append(entry)
    conv["history"] = history[-HISTORY_LIMIT:]
    return conv


def thresholds_for(conv: Mapping[str, Any]) -> dict[str, float | None]:
    """返回当前状态下前端要画的阈值刻度 {"down", "up"}。

    down=0.25 表示再向左会降档；已在当前 base 允许的最左区间时为 None。
    up=0.75 表示再向右会升档；已在当前 base 允许的最右区间时为 None。
    """
    conv = conv if isinstance(conv, Mapping) else {}
    base = str(conv.get("base") or "较高").strip()
    if base not in TIERS:
        base = "较高"
    effective = str(conv.get("effective") or _tier_of(float(conv.get("position", START_POSITIONS[base]))))
    if effective not in TIERS:
        effective = _tier_of(float(conv.get("position", START_POSITIONS[base])))
    leftmost = "较高" if base == "极高" else "一般"
    rightmost = "较高" if base == "一般" else "极高"
    return {
        "down": None if effective == leftmost else DOWN_THRESHOLD,
        "up": None if effective == rightmost else UP_THRESHOLD,
    }


__all__ = [
    "TIERS", "DOWN_THRESHOLD", "UP_THRESHOLD", "START_POSITIONS", "OUTCOMES",
    "HISTORY_LIMIT", "init_state", "settle", "thresholds_for",
]
