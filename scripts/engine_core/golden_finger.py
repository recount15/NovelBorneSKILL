"""动态金手指推荐与自定义确认状态机。

确定性实现：候选由世界观关键词、主角性格和难度共同挑选，不依赖模型调用，
因此可离线测试与复现。模型只能在已确认的规格上叙事，不能自行扩权。

金手指缩放（rules/work_library.md M130）：GF(D) = D^1.15，D 为宿敌强度
（浮点 0.01–9.99，越小越强）。有效强度上限 E = WS × GF(D) × κ。
D 越小（宿敌越强）→ GF(D) 越小 → 金手指被压得越狠；D 越大（宿敌越弱）
→ GF(D) 越接近 1 → 金手指可以放开。spec 的 cost/cooldown 字段直接反映
缩放结果，供开局叙事执行。
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

NONE_LABEL = "无（凡人开局）"
CUSTOM_LABEL = "自定义（由系统正式化后确认）"
MAX_ATTEMPTS = 3

# GF(D) = D^1.15（M130 矩阵）；GF 值越小 = 金手指越弱
GF_EXPONENT = 1.15


def gf_scale(nemesis_d: int | float | str = 4.0) -> float:
    """金手指缩放系数 GF(D) = D^1.15。

    D 为宿敌强度（0.01–9.99，越小宿敌越强）。D 小 → GF 小 → 金手指弱
    （宿敌碾压时金手指必须微末才平衡）；D 大 → GF 越大 → 金手指放开。
    D 缺省按 D4 普通难度。返回值 clamp 到 [0.01, 13] 防溢出
    （9.99^1.15≈12.6）。
    """
    d = _difficulty_float(nemesis_d)
    return round(max(0.01, min(13.0, math.pow(d, GF_EXPONENT))), 4)


@dataclass(frozen=True)
class GoldenFingerSpec:
    id: str
    name: str
    effect: str
    scope: str
    cost: str
    cooldown: str
    limits: str
    fit: str
    source: str = "generated"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def label(self) -> str:
        return f"{self.name}｜{self.effect}"


NONE_SPEC = GoldenFingerSpec(
    id="gf-none", name=NONE_LABEL, effect="不获得任何超常能力，仅靠自身与世界资源",
    scope="无", cost="无", cooldown="无",
    limits="宿敌、伙伴、女主同样不得拥有金手指",
    fit="适合硬核体验与纯策略推演", source="none",
)

# 候选池：每项附带世界观倾向标签，便于按作品加权而非固定十项。
_POOL: tuple[tuple[str, str, str, str, str, str, str, tuple[str, ...]], ...] = (
    ("观察回响", "读取刚发生事件的可验证因果链", "当前场景", "精神负荷累积、信息噪声干扰",
     "每场景一次", "不能读取未来，只能解释已发生事件", "谨慎、探索型主角", ("推理", "悬疑", "现实")),
    ("有限重演", "付出代价后重试最近一次关键选择", "单次行动", "记忆、寿元或资源代价",
     "每日一次", "不能抹除他人既成事实", "规则、苟稳型主角", ("超凡", "系统", "现实")),
    ("契约账本", "把承诺、债务与交换条件结构化追踪", "关系与交易", "必须承担违约后果",
     "每个对象一次", "不能凭空制造忠诚", "谋略、义守型主角", ("权谋", "商战", "江湖")),
    ("技能映射", "将已掌握知识映射为当前世界可用技巧", "已有知识", "学习时间与失败风险",
     "按冷却恢复", "不得越过世界力量上限", "成长、行动型主角", ("修炼", "超凡", "系统")),
    ("线索聚焦", "从已知信息指出下一条最有价值的调查路径", "调查场景", "消耗注意力并暴露关注方向",
     "每回合一次", "不直接给出答案", "探索、谋略型主角", ("推理", "悬疑", "现实")),
    ("气机预警", "对指向自身的杀意与陷阱提前示警", "自身安危", "预警越强反噬越重",
     "每场冲突一次", "只提示威胁方向，不提供解法", "苟稳、行动型主角", ("修炼", "江湖", "超凡")),
    ("物资暗格", "随身存取有限体积的既得物资", "随身物品", "容量固定，取放需要时间",
     "无冷却但有容量上限", "不能存放活物或凭空生成物资", "务实、成长型主角", ("系统", "现实", "商战")),
    ("人心刻度", "读出对话者当前态度倾向与底线区间", "社交场景", "读取失准会造成误判",
     "每人每场一次", "不能强制改变对方意志", "谋略、情感型主角", ("权谋", "商战", "现实")),
)

_WORLD_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("修炼", ("修炼", "灵气", "修仙", "武道", "境界", "丹药", "宗门")),
    ("超凡", ("魔法", "咒语", "神秘", "超能", "异能", "克苏鲁", "血脉")),
    ("系统", ("系统", "面板", "任务", "抽奖", "签到", "副本")),
    ("权谋", ("朝堂", "权谋", "夺嫡", "官场", "政治", "军政")),
    ("商战", ("商战", "公司", "生意", "资本", "市场", "创业")),
    ("推理", ("推理", "案件", "凶手", "侦探", "线索")),
    ("悬疑", ("悬疑", "诡异", "禁忌", "灵异", "恐怖")),
    ("江湖", ("江湖", "武林", "门派", "刀剑", "镖")),
    ("现实", ("都市", "现实", "校园", "职场", "年代")),
)

_PERSONA_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("谨慎、探索型主角", ("谨慎", "探索", "观察", "好奇")),
    ("规则、苟稳型主角", ("规则", "苟", "稳健", "保命", "谨小慎微")),
    ("谋略、义守型主角", ("谋", "布局", "义", "护短")),
    ("成长、行动型主角", ("莽", "行动", "成长", "热血", "直接")),
    ("探索、谋略型主角", ("解构", "钻研", "机制", "缝隙")),
    ("苟稳、行动型主角", ("警觉", "敏感", "危机")),
    ("务实、成长型主角", ("务实", "算计", "经营", "攒")),
    ("谋略、情感型主角", ("情感", "共情", "人心", "交际", "乐子")),
)


def _tags(text: str, table: Iterable[tuple[str, tuple[str, ...]]]) -> list[str]:
    lowered = str(text or "").lower()
    return [name for name, words in table if any(word.lower() in lowered for word in words)]


def _difficulty_num(difficulty: Any) -> int:
    text = str(difficulty or "")
    for ch in text:
        if ch.isdigit():
            return max(1, min(9, int(ch)))
    return 4


def _difficulty_float(value: Any) -> float:
    """解析宿敌强度 D（浮点 0.01–9.99）；数字缺失时按玩家难度取 10-D。"""
    text = str(value or "")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if nums:
        return max(0.01, min(9.99, float(nums[0])))
    return 4.0


def _scaled_cost(base_cost: str, gf: float) -> str:
    """GF 越小（金手指越弱），代价描述越重。"""
    if gf >= 0.85:
        return base_cost
    if gf >= 0.5:
        return f"{base_cost}；GF{gf:.2f} 压制：代价上浮（难度压金手指）"
    return f"{base_cost}；GF{gf:.2f} 强压：代价显著加重、效果上限受限"


def _scaled_cooldown(base_cd: str, gf: float) -> str:
    """GF 越小，冷却越长。"""
    if gf >= 0.85:
        return base_cd
    if gf >= 0.5:
        return f"{base_cd}（GF{gf:.2f}：冷却延长约半）"
    return f"{base_cd}（GF{gf:.2f}：冷却翻倍，慎用）"


def _scaled_limits(base_limits: str, gf: float) -> str:
    if gf >= 0.85:
        return base_limits
    return f"{base_limits}；本局宿敌强度压金手指至 GF{gf:.2f}（E=WS×GF(D)），不得越档"


def recommend(world: str = "", persona: str = "", difficulty: str = "",
              limit: int = 5, nemesis_d: int | float | str = 4.0) -> list[GoldenFingerSpec]:
    """按世界观倾向、性格与难度给出候选（默认 5 个），顺序稳定可复现。

    ``nemesis_d``：宿敌强度 D（浮点），驱动 GF(D)=D^1.15 缩放——宿敌越强
    （D 越小），金手指被压得越狠（代价更重、冷却更长、限制更多）。
    """
    world_tags = _tags(world, _WORLD_TAGS)
    persona_tags = _tags(persona, _PERSONA_TAGS)
    level = _difficulty_num(difficulty)
    gf = gf_scale(nemesis_d)
    scored: list[tuple[int, int, tuple]] = []
    for index, row in enumerate(_POOL):
        fit, tags = row[6], row[7]
        score = sum(2 for tag in tags if tag in world_tags)
        score += 3 if fit in persona_tags else 0
        # 高难度偏向信息与规避型能力，低难度容许更直接的资源型能力。
        if level >= 7 and row[0] in ("气机预警", "线索聚焦", "观察回响"):
            score += 2
        if level <= 3 and row[0] in ("物资暗格", "技能映射"):
            score += 1
        # GF 缩放的候选偏好：GF 小（宿敌强）时，代价轻的信息型能力优先
        if gf < 0.5 and row[0] in ("观察回响", "线索聚焦", "气机预警"):
            score += 1
        scored.append((score, -index, row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    prefix = "世界规则适配" if world_tags and world_tags[0] in ("修炼", "超凡", "系统") else "现实因果适配"
    picked = [row for _score, _order, row in scored[: max(1, int(limit))]]
    result: list[GoldenFingerSpec] = []
    for i, (name, effect, scope, cost, cooldown, limits, fit, _tag) in enumerate(picked, 1):
        result.append(GoldenFingerSpec(f"gf-{i}", f"{prefix}·{name}", effect, scope,
                                       _scaled_cost(cost, gf), _scaled_cooldown(cooldown, gf),
                                       _scaled_limits(limits, gf), f"适合{fit}｜GF={gf:.2f}"))
    return result


def choices(world: str = "", persona: str = "", difficulty: str = "",
            limit: int = 5, nemesis_d: int | float | str = 4.0) -> list[str]:
    """给 UI 的下拉项：5 个推荐 + 无 + 自定义。"""
    return [spec.label() for spec in recommend(world, persona, difficulty, limit, nemesis_d)] + [NONE_LABEL, CUSTOM_LABEL]


def is_none(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text == NONE_LABEL or text.startswith("无（") or text == "无"


def is_custom(value: Any) -> bool:
    return str(value or "").strip() == CUSTOM_LABEL


def propose_custom(text: str, world: str = "", persona: str = "", difficulty: str = "",
                   attempt: int = 1, nemesis_d: int | float | str = 4.0) -> dict[str, Any]:
    """把玩家想法正式化为待确认提案；最多三次。GF(D) 缩放同样适用。"""
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("自定义金手指不能为空")
    attempt = int(attempt)
    if attempt < 1 or attempt > MAX_ATTEMPTS:
        raise ValueError("自定义金手指最多允许三次提交")
    level = _difficulty_num(difficulty)
    gf = gf_scale(nemesis_d)
    cooldown = "每场景一次" if level <= 3 else ("每日一次" if level <= 6 else "每章一次")
    spec = GoldenFingerSpec(
        "gf-custom", f"自定义·{clean[:18]}", clean,
        "由玩家描述界定，且不得覆盖全局",
        _scaled_cost(f"按世界规则等价代价（难度 D{level} 加权）", gf),
        _scaled_cooldown(cooldown, gf),
        _scaled_limits("不得抹除既成事实、不得越过世界上限、必须可验证", gf),
        f"适配世界：{world or '待确认'}；性格：{persona or '待确认'}；GF={gf:.2f}",
        source="custom")
    return {"status": "await_confirmation", "attempt": attempt,
            "remaining": max(0, MAX_ATTEMPTS - attempt), "spec": spec.to_dict(),
            "gf": gf, "nemesis_d": _difficulty_float(nemesis_d)}


def confirm_custom(proposal: Mapping[str, Any], confirmed: bool) -> dict[str, Any]:
    if not isinstance(proposal, Mapping) or proposal.get("status") != "await_confirmation":
        raise ValueError("无可确认的自定义金手指提案")
    result = dict(proposal)
    result["status"] = "confirmed" if confirmed else "rejected"
    return result


def resolve(selection: Any, proposal: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """把 UI 选择归一化为开局使用的金手指结论。

    返回 ``{"label", "spec", "none", "blocked", "ready", "reason"}``：
    - ``none`` 为真时，宿敌/伙伴/女主一律不得拥有金手指（``blocked``）。
    - 自定义未确认时 ``ready`` 为假，开局必须拦截。
    """
    if is_none(selection):
        return {"label": NONE_LABEL, "spec": NONE_SPEC.to_dict(), "none": True,
                "blocked": True, "ready": True, "reason": "已选择无金手指"}
    if is_custom(selection):
        if isinstance(proposal, Mapping) and proposal.get("status") == "confirmed":
            spec = dict(proposal.get("spec") or {})
            return {"label": str(spec.get("name") or CUSTOM_LABEL), "spec": spec, "none": False,
                    "blocked": False, "ready": True, "reason": "自定义金手指已确认"}
        return {"label": CUSTOM_LABEL, "spec": {}, "none": False, "blocked": False,
                "ready": False, "reason": "自定义金手指尚未确认"}
    label = str(selection or "").strip()
    return {"label": label, "spec": {"name": label.split("｜")[0], "source": "generated"},
            "none": False, "blocked": False, "ready": True, "reason": "已选择推荐金手指"}


def apply_block(members: Iterable[Mapping[str, Any]] | None, blocked: bool) -> list[dict[str, Any]]:
    """在“无金手指”时，抹掉伙伴/女主/宿敌配置里的金手指字段。"""
    result = []
    for item in list(members or []):
        row = dict(item)
        if blocked:
            row.pop("golden_finger", None)
            row["golden_finger_blocked"] = True
        result.append(row)
    return result


__all__ = ["GoldenFingerSpec", "NONE_SPEC", "NONE_LABEL", "CUSTOM_LABEL", "MAX_ATTEMPTS",
           "GF_EXPONENT", "gf_scale", "recommend", "choices", "is_none", "is_custom",
           "propose_custom", "confirm_custom", "resolve", "apply_block"]
