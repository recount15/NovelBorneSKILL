# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only next-step diagnostics and incomplete data templates, never approvals."""
import copy

import runtime as rt
import preparation


def doctor(session):
    with rt.locked(session) as directory:
        state, _ = rt.load_session(directory)
        if state["version"] != 2:
            return {"next_command": "export", "reason": "legacy_readonly", "blockers": ["v2_session_required"]}
        text, index = rt.prepared_data(directory)
        rt.require(index == state["source_index"], "signed_source_index_mismatch")
        prep = state["preparation"]
        progress = preparation.progress(state)
        next_command, reason = "input", "await_user_message"
        if state["phase"] == "awaiting_opening":
            if not progress["complete"]:
                next_command, reason = "source-window / distill", "source_scope_coverage_incomplete"
            elif not prep["setup_confirmed"]:
                next_command, reason = "input", "await_user_确认设定"
            elif not prep["gf_confirmed"]:
                next_command, reason = "input", "await_user_确认金手指_or_确认无金手指"
            elif len(prep["cards"]) != 1 + len(state["config"]["characters"]):
                next_command, reason = "template --kind card / card", "configured_character_cards_incomplete"
            elif not prep["cast_confirmed"]:
                next_command, reason = "input", "await_user_确认角色"
            else:
                next_command, reason = "input", "await_user_确认开局"
        elif state["phase"] == "paused":
            next_command, reason = "input", "paused_await_user_继续本局"
        else:
            p = state.get("pipeline")
            if p:
                if p["revision"] != state["revision"]:
                    next_command, reason = "context --fresh", "stale_pipeline_token"
                else:
                    next_command = {"context": "plan", "planned": "stage", "staged": "review",
                                    "reviewed": "commit", "rejected": "context --fresh"}[p["stage"]]
                    reason = "pipeline_" + p["stage"]
            elif state["turn"] == 0 or state["pending_action"] is not None:
                next_command, reason = "context", "narrative_work_pending"
            else:
                chapter = next(c for c in index["chapters"] if c["id"] == state["mechanical"]["chapter_id"])
                if state["mechanical"]["chapter_turn"] >= chapter["turn_budget"]:
                    final = chapter["id"] == index["chapters"][-1]["id"]
                    reason = "book_budget_complete_export_or_pause" if final else "await_user_确认翻章_prepare_next_chapter"
        return {"next_command": next_command, "reason": reason,
                "blockers": [] if reason.startswith("pipeline_") else [reason],
                "phase": state["phase"], "revision": state["revision"], "turn": state["turn"],
                "preparation": progress, "missing_cards": [n for n in
                    [state["config"]["protagonist"]["name"], *[c["name"] for c in state["config"]["characters"]]]
                    if n not in prep["cards"]], "state_changed": False,
                "notice": "These are tool prerequisites, not evidence of semantic quality or user consent."}


def template(session, kind, name=None):
    with rt.locked(session) as directory:
        state, _ = rt.load_session(directory)
        rt.require(state["version"] == 2, "v2_session_required")
        prep, p = state["preparation"], state.get("pipeline")
        result = {}
        complete = False
        if kind == "card":
            name = name or state["config"]["protagonist"]["name"]
            cfg = next((c for c in [state["config"]["protagonist"], *state["config"]["characters"]]
                        if c["name"] == name), None)
            rt.require(cfg is not None, "undeclared_character")
            role = "protagonist" if name == state["config"]["protagonist"]["name"] else cfg["role"]
            result = {"name": name, "role": role, "origin": cfg["origin"],
                      "description": cfg["description"], "personality": "", "goal": "",
                      "abilities": [], "limits": [], "relationships": [], "knowledge": [], "source_refs": [],
                      "desire": "", "fear": "", "decision_principle": "", "taboo": "", "voice_samples": [],
                      "behavior_boundaries": [], "mind_model": "", "decision_policy": "", "voice_transfer": ""}
        elif kind == "distill":
            pending = [r for rid, r in prep["issued"].items() if rid not in prep["chunks"]]
            rt.require(bool(pending), "source_window_receipt_required")
            receipt = pending[-1]
            result = {"receipt_id": receipt["receipt_id"], "summary": "", "facts": [], "anchors": []}
        elif kind == "plan":
            rt.require(p is not None and p["stage"] == "context", "context_required")
            result = {"token": p["token"], "expected_revision": state["revision"],
                      "source_refs": [], "intent": state["pending_action"]["text"] if state["pending_action"] else "__opening__",
                      "outcome": "", "resolution": "opening" if not state["pending_action"] else "limited",
                      "costs": [], "character_reactions": [],
                      "ripple": {"breadth": 0, "persistence": 0, "canon_conflict": 0, "pressure": 0},
                      "anchor": {"text": "", "outcome": "none"}, "anchor_updates": [], "gf_used": False}
        elif kind == "draft":
            rt.require(p is not None and p["stage"] in ("planned", "staged", "reviewed"), "plan_required")
            if "draft" in p:
                result = copy.deepcopy(p["draft"])
                result["expected_revision"] = state["revision"]
                complete = p["stage"] == "reviewed"
            else:
                result = {"pipeline_token": p["token"], "expected_revision": state["revision"], "text": "",
                          "summary": "", "world_updates": [],
                          "source_refs": [{k: r[k] for k in ("chapter_id", "start", "end")} for r in p["plan"]["source_refs"]],
                          "options": [{"id": n, "text": "", "kind": "plot" if i < 4 else "personality"}
                                      for i, n in enumerate("ABCDEF")]}
        elif kind == "review":
            rt.require(p is not None and p["stage"] == "staged", "staged_draft_required")
            result = {"token": p["token"], "expected_revision": state["revision"],
                      "draft_sha256": p["draft_sha256"], "issues": [],
                      "notes": {key: "" for key in ("continuity", "knowledge", "character", "gf", "causality")}}
        else:
            raise rt.RuntimeError_("unknown_template")
        return {"kind": kind, "data": result, "complete": complete, "state_changed": False,
                "notice": "Save only data to an input file. Fill missing evidence and prose; defaults are not a completed assessment."}
