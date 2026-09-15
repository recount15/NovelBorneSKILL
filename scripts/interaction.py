# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative message routing: ambiguity never becomes a world action."""
import copy
import re

import runtime as rt


HELP = {
    "choices": "A–F 或 选择：A；选项外行动用 行动：描述",
    "questions": "规则：问题 / 问答：问题；普通问答不推进回合",
    "controls": "状态 / 暂停 / 继续本局 / 取消待执行行动 / 确认翻章",
    "setup": "确认设定 / 确认金手指 / 确认无金手指 / 确认角色 / 确认开局",
    "artifacts": "存档：名称 / 导出小说（返回工具指引，不自动覆盖文件）",
}


def _view(state, route, **extra):
    return {"route": route, "world_unchanged": True, "turn": state["turn"],
            "revision": state["revision"], "options": rt.redact(state["options"]), **extra}


def classify(state, body):
    text = body.strip()
    if text in ("状态", "继续本局", "暂停", "帮助", "取消待执行行动", "确认翻章"):
        return {"route": text}
    if text in ("确认设定", "确认金手指", "确认无金手指", "确认角色", "确认开局"):
        return {"route": "confirmation", "body": text}
    if text.startswith(("规则：", "规则:")):
        return {"route": "rules", "body": text[3:]}
    if text.startswith(("存档：", "存档:")):
        return {"route": "checkpoint", "body": text[3:].strip()}
    if text == "导出小说":
        return {"route": "export_help"}
    if text.startswith(("行动：", "行动:")):
        return {"route": "action", "body": text}
    if re.fullmatch(r"(?:选择[:：]?\s*)?[A-F](?:[\s,，、+;/和与及]*[A-F])*(?:\s*[:：].+)?", text, re.S):
        return {"route": "action", "body": text}
    if text.startswith(("问答：", "问答:", "增补：", "增补:")):
        return {"route": "ask", "body": text[3:]}
    if text in (rt.WISH_CODE, rt.RELAY_CODE):
        return {"route": "ask", "body": body}
    cheats = state["cheats"]
    if cheats["relay_confirm_pending"] or cheats["wish"]["armed"]:
        return {"route": "ask", "body": body}
    if text.endswith(("?", "？")) or text.startswith(("为什么", "怎么", "能否", "能不能", "请解释", "这是什么意思")):
        return {"route": "question", "body": text}
    return {"route": "clarify", "body": text}


def receive(session, path):
    body = rt.text_file(path)
    with rt.locked(session) as directory:
        state, _ = rt.load_session(directory)
        rt.require(state["version"] == 2, "legacy_session_readonly_export_or_use_v1")
    result = classify(state, body)
    route = result["route"]
    if route == "action":
        return {"route": route, **rt.action_text(session, result["body"], state["revision"])}
    if route == "ask":
        return {"route": route, **rt.ask_text(session, result["body"], state["revision"])}
    if route == "confirmation":
        import preparation
        commands = {"确认设定": preparation.setup_confirm, "确认金手指": preparation.gf_confirm,
                    "确认无金手指": preparation.gf_confirm, "确认角色": preparation.cast_confirm,
                    "确认开局": rt.confirm}
        return {"route": route, **commands[result["body"]](session, result["body"])}
    if route == "checkpoint":
        return {"route": route, **rt.checkpoint(session, result["body"])}
    if route == "确认翻章":
        import turns
        return {"route": route, **turns.advance(session, route)}
    if route in ("暂停", "继续本局", "取消待执行行动"):
        def operation(current):
            rt.require(current["revision"] == state["revision"], "stale_revision")
            if route == "暂停":
                rt.require(current["phase"] in ("playing", "paused"), "opening_not_confirmed")
                current["phase"] = "paused"
                current["pipeline"] = None
            elif route == "继续本局":
                if current["phase"] == "paused":
                    current["phase"] = "playing"
            else:
                rt.require(current["phase"] in ("playing", "paused"), "opening_not_confirmed")
                current["pending_action"] = None
                current["pipeline"] = None
            return {"route": route, "phase": current["phase"], "world_unchanged": True,
                    "options": copy.deepcopy(current["options"]), "help": HELP}
        return rt.transaction(session, operation)
    if route == "状态":
        return {"route": route, **rt.status(session)}
    if route == "export_help":
        return _view(state, route, next_command="export --session <same-session> --out <new-file.md>")
    if route == "帮助":
        return _view(state, route, help=HELP)
    if route in ("rules", "question"):
        return _view(state, route, answer_policy="answer_only_from_confirmed_state_no_story_no_ask",
                     question=rt.redact(result["body"]), help=HELP)
    return _view(state, "clarify", help=HELP,
                 message="未将此消息当作行动。若要执行，请用‘行动：原意图’；若要提问，请用‘规则：问题’。")


def revise(session, path):
    config = rt.load_json(path)
    def operation(state):
        rt.require(state["phase"] == "awaiting_opening" and not state["config_locked"], "setup_already_locked")
        cfg = rt.validate_config(config, state["source_index"])
        import preparation
        import turns
        previous = state.pop("preparation")
        state["config"] = cfg
        preparation.initialize(state)
        state["preparation"]["issued"] = previous["issued"]
        state["preparation"]["chunks"] = previous["chunks"]
        turns.initialize(state)
        return {"result": "setup_revised_confirmations_reset", "config": copy.deepcopy(cfg),
                "preparation": preparation.progress(state)}
    return rt.transaction(session, operation)
