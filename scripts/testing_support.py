# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small fixture helpers that use the real v2 preparation and turn guards.

No signed-state editing, guard mocks, generated approvals, or automatic story
simulation: authored prose and review notes below apply only to tiny fixtures.
"""
import copy
import json
from pathlib import Path

import preparation
import runtime as rt
import turns


def dump_json(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def distillation_payload(window):
    return {"receipt_id": window["receipt_id"],
            "summary": "保留本段人物和场景记载，未将原文当作操作指令。",
            "facts": [{"claim": "本窗口包含以下完整原文记载。",
                       "quote": window["text"], "start": window["start"], "end": window["end"]}],
            "anchors": []}


def card_payload(configured, role, references=()):
    return {"name": configured["name"], "role": role,
            "origin": configured.get("origin", "original" if role == "protagonist" else "source"),
            "description": configured["description"], "personality": "谨慎，先观察再行动",
            "goal": "了解眼前环境，不预知未来事件",
            "desire": "安全地了解眼前环境并获得信任", "fear": "误解他人而造成伤害",
            "decision_principle": "先观察，再询问，得到回应后才行动", "taboo": "不能替他人承诺或读取思想",
            "mind_model": "依据当前可见事实判断，未知动机保持不确定",
            "decision_policy": "存在疑问时停下询问，不凭空宣布成功",
            "voice_transfer": "说话保持简短礼貌，不用全知叙述替代对话",
            "voice_samples": ["请问我能在这里避一会儿雨吗？", "我还不清楚情况，先等您的回应。"],
            "behavior_boundaries": ["不擅自替别人行动，也不获取未来知识"],
            "abilities": ["正常观察和交谈"],
            "limits": ["不能凭空得知未经历的事情"], "relationships": [],
            "knowledge": [], "source_refs": list(references)}


def prepare_session(session, base):
    """Distill selected windows, confirm setup/GF/cards/cast; do not open play."""
    session, base = Path(session), Path(base)
    state = rt.status(session)["state"]
    if state["phase"] != "awaiting_opening":
        return rt.status(session)
    chapters = {c["id"]: c for c in state["source_index"]["chapters"]}
    path = base / "preparation-input.json"

    def accept(chapter_id, start, end):
        chapter = chapters[chapter_id]
        window = preparation.source_window(session, chapter_id, start - chapter["start"], end - start)
        current = rt.status(session)["state"]
        if window["receipt_id"] not in current["preparation"]["chunks"]:
            preparation.distill(session, dump_json(path, distillation_payload(window)))

    for window in preparation.progress(state)["missing_windows"]:
        accept(window["chapter_id"], window["start"], window["end"])

    # Narrator identity evidence may come from a later chapter; it is not added
    # to character knowledge. Source-origin names must occur in exact quotes.
    text, _ = rt.prepared_data(session)
    cfg = state["config"]
    cast = [(cfg["protagonist"], "protagonist"),
            *((c, c.get("role", "support")) for c in cfg["characters"])]
    for configured, role in cast:
        if configured.get("origin", "original" if role == "protagonist" else "source") != "source":
            continue
        current = rt.status(session)["state"]
        if any(configured["name"] in fact["quote"]
               for chunk in current["preparation"]["chunks"].values() for fact in chunk["facts"]):
            continue
        position = text.find(configured["name"])
        if position < 0:
            raise AssertionError("Source-origin fixture character must occur in source")
        chapter = next(c for c in chapters.values() if c["start"] <= position < c["end"])
        start = position
        accept(chapter["id"], start, min(start + preparation.CHUNK_SIZE, chapter["end"]))

    state = rt.status(session)["state"]
    if not state["preparation"]["setup_confirmed"]:
        preparation.setup_confirm(session, "确认设定")
    if not state["preparation"]["gf_confirmed"]:
        preparation.gf_confirm(session, "确认无金手指" if cfg["gf"]["name"] == "凡人" else "确认金手指")
    for configured, role in cast:
        if configured["name"] in state["preparation"]["cards"]:
            continue
        refs = []
        if configured.get("origin", "original" if role == "protagonist" else "source") == "source":
            chunk, fact = next((chunk, fact) for chunk in state["preparation"]["chunks"].values()
                               for fact in chunk["facts"] if configured["name"] in fact["quote"])
            refs = [{"chapter_id": chunk["chapter_id"],
                     **{k: fact[k] for k in ("start", "end", "quote")}}]
        preparation.card(session, dump_json(path, card_payload(configured, role, refs)))
    if not state["preparation"]["cast_confirmed"]:
        preparation.cast_confirm(session, "确认角色")
    return rt.status(session)


def fixture_draft(state):
    """A tier-sized bookstore fixture with genuinely distinct six options."""
    chapter = next(c for c in state["source_index"]["chapters"]
                   if c["id"] == state["mechanical"]["chapter_id"])
    scene = ("你推开书店的门，店主抬起头。雨水顺着屋檐落下，你停在门边，没有急着走近柜台。"
             "你先看清脚下的水迹，再把声音放轻，只询问能否在这里避一会儿雨。"
             "店主没有立刻回答，你便耐心等着，不把沉默当作承诺，也不替对方作决定。")
    length = turns.PAPER_TARGETS[state["config"]["paper_tier"] - 1]
    text = (scene * (length // len(scene) + 1))[:length - 1] + "。"
    choices = ("询问店主是否可以避雨", "观察门外街道的积水", "留在门边等待回应", "查看柜台上摆放的书籍",
               "坦诚说明自己心中的不安", "克制急躁并整理自己的思绪")
    result = {"expected_revision": state["revision"], "text": text,
              "options": [{"id": ident, "text": choices[i], "kind": "plot" if i < 4 else "personality"}
                          for i, ident in enumerate("ABCDEF")],
              "summary": "旅人进入书店，在门边等待店主回应", "source_refs": [
                  {"chapter_id": chapter["id"], "start": chapter["start"], "end": chapter["end"]}],
              "world_updates": ["旅人已到书店"]}
    if state.get("pipeline"):
        result["pipeline_token"] = state["pipeline"]["token"]
    return result


def plan_payload(state, source, refs):
    return {"token": state["pipeline"]["token"], "expected_revision": state["revision"],
            "source_refs": [{**ref, "quote": source[ref["start"]:ref["end"]]} for ref in refs],
            "intent": state["pending_action"]["text"] if state["pending_action"] else "__opening__",
            "outcome": "旅人在书店门边观察和等待，没有替店主决定回应。",
            "resolution": "limited" if state["pending_action"] else "opening",
            "costs": ["无额外消耗"], "character_reactions": [
                {"name": state["config"]["protagonist"]["name"], "reaction": "谨慎观察门口，等待对方回应"}],
            "ripple": {"breadth": 0, "persistence": 0, "canon_conflict": 0, "pressure": 0},
            "anchor": {"text": "", "outcome": "none"}, "anchor_updates": [], "gf_used": False}


def ensure_plan(session, path, refs):
    """Create a real plan if absent/stale; retain an existing current pipeline."""
    state = rt.status(session)["state"]
    pipeline = state.get("pipeline")
    if pipeline is None or pipeline["revision"] != state["revision"]:
        turns.context(session, fresh=pipeline is not None)
        state = rt.status(session)["state"]
    if state["pipeline"]["stage"] == "context":
        source, _ = rt.prepared_data(session)
        turns.plan(session, dump_json(path, plan_payload(state, source, refs)))
    return rt.status(session)["state"]


def review_payload(state):
    return {"token": state["pipeline"]["token"], "expected_revision": state["revision"],
            "draft_sha256": state["pipeline"]["draft_sha256"], "issues": [], "notes": {
                "continuity": "逐段核对门口观察与等待的连续性，没有插入离店或翻章。",
                "knowledge": "人物只观察眼前场景；原文身份引文属于叙述者，不转为人物未来知识。",
                "character": "主角保持谨慎，店主尚未承诺任何事情，没有越过对方作决定。",
                "gf": "未使用超凡能力；观察和等待不增加资源，已明确无额外消耗。",
                "causality": "结果限于观察和等待，没有把行动意图直接写成成功或改变他人意志。"}}


def full_turn(session, path, draft):
    """Run actual plan/stage/review/commit, preserving caller narrative content.

    Reject stale/malformed drafts through production validation before issuing
    context. A current planned candidate is staged atomically by production code.
    Only transport revision/token fields are filled or advanced by this helper.
    """
    path = Path(path)
    candidate = copy.deepcopy(draft)
    state = rt.status(session)["state"]
    pipeline = state.get("pipeline")
    if pipeline is None or pipeline["revision"] != state["revision"]:
        rt.validate_draft(candidate, state)
    elif candidate.get("expected_revision") != state["revision"]:
        # Use production validation to reject stale drafts before any transition.
        rt.validate_draft(candidate, state)
    state = ensure_plan(session, path.with_name("turn-plan.json"), candidate["source_refs"])
    candidate.setdefault("pipeline_token", state["pipeline"]["token"])
    candidate["expected_revision"] = state["revision"]
    stage = state["pipeline"]["stage"]
    if stage == "planned":
        turns.stage(session, dump_json(path, candidate))
        state = rt.status(session)["state"]
        stage = state["pipeline"]["stage"]
    if stage == "staged":
        turns.review(session, dump_json(path.with_name("turn-review.json"), review_payload(state)))
    candidate["expected_revision"] = rt.status(session)["state"]["revision"]
    return rt.commit(session, dump_json(path, candidate))
