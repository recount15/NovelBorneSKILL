# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revision-bound, stdlib-only v2 narrative pipeline.

This is a deterministic transport/provenance guard, NOT a full automatic story
engine. Classifications, resource costs, review notes, knowledge and causality
remain model-authored, unverified semantics. A same-chapter quote can still
reveal a later event (especially relative_time='before'); a reviewer must check
that explicitly. Reviews are structured self-reports, not independent proof.

Paper targets come from references/setup.md. The explicit inclusive +/-25%
Unicode-code-point envelope is this runtime's policy, not an upstream formula.
Only committed candidates affect mechanical totals. Source offsets are global,
start-inclusive/end-exclusive. A changed revision invalidates the whole token.

Integration: rt.create calls initialize; rt.action calls require_action_budget;
rt.commit validates the draft then calls commit_ready BEFORE mutating events or
turns, in the same transaction, and copies last_turn_audit into its event. Each
pipeline response gives the next expected revision. Commit resubmits the exact
staged draft with only expected_revision updated; pipeline_token stays unchanged.
Review issue rejection intentionally records stage='rejected' before raising.
Use context(..., fresh=True) to abandon any existing pipeline, including rejected
or stale candidates. Plan resolution is opening/success/limited/failed; denied
ripple permits only limited/failed. anchor_updates are model-authored disposition
records (fulfilled/hint_only), not proof that events happened. Their presence is
required for all prepared chapter anchors at the final budget turn and advance.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import unicodedata
import uuid

import runtime as rt
import mechanics

PAPER_TARGETS = (400, 650, 950, 1350, 1850, 2400)
PAPER_RANGES = {i: ((n * 3 + 3) // 4, n * 5 // 4)
                for i, n in enumerate(PAPER_TARGETS, 1)}
SEMANTIC_NOTICE = (
    "Model-authored classifications and review notes are unverified; numeric "
    "calculations and structural checks do not prove continuity, knowledge, "
    "character motivation, resource accounting, or causal validity. No full "
    "automatic engine or independent reviewer is claimed."
)
REVIEW_CATEGORIES = ("continuity", "knowledge", "character", "gf", "causality")


def initialize(state):
    """Called once by rt.create after v2 config and source_index exist."""
    rt.require(state.get("version") == 2, "v2_session_required")
    state["pipeline"] = None
    state["mechanical"] = {
        "ripple_total": 0,
        "convergence": mechanics.calculate_convergence(
            {"base": state["config"]["convergence"]})["conv"],
        "chapter_id": state["config"]["setup"]["target_chapter"],
        "chapter_turn": 0,
        "anchor_ledger": {},
    }


def _ready(state):
    rt.require(state.get("version") == 2, "v2_session_required")
    rt.require(state.get("phase") == "playing", "opening_not_confirmed")
    rt.require(state.get("config_locked") is True and
               state.get("locked_config_sha256") == rt.sha(rt.canonical(state["config"])),
               "locked_config_required")
    import preparation
    preparation.ready(state)


def _chapter(state):
    chapter_id = state["mechanical"]["chapter_id"]
    chapter = next((c for c in state["source_index"]["chapters"]
                    if c["id"] == chapter_id), None)
    rt.require(chapter is not None, "unknown_current_chapter")
    return chapter


def require_action_budget(state):
    """rt.action calls this before accepting an action, preventing a dead end."""
    rt.require(state.get("version") == 2, "v2_session_required")
    chapter = _chapter(state)
    rt.integer(state["mechanical"]["chapter_turn"], 0, chapter["turn_budget"])
    rt.require(state["mechanical"]["chapter_turn"] < chapter["turn_budget"],
               "chapter_budget_exhausted_confirm_advance")


def _source(session, state):
    text, index = rt.prepared_data(session)
    rt.require(index == state["source_index"], "signed_source_index_mismatch")
    return text


def _binding(state):
    # Includes pending action, cheat state, locked config, cards, all accepted
    # preparation text hashes, ledger, chapter and every other authority field.
    return rt.sha(rt.canonical({k: v for k, v in state.items()
                               if k not in ("pipeline", "revision")}))


def _current(state, token, expected_revision, required_stage):
    _ready(state)
    rt.integer(expected_revision, 0, 2**53)
    rt.require(expected_revision == state["revision"], "stale_revision")
    p = state.get("pipeline")
    rt.require(type(p) is dict and p.get("token") == token, "invalid_pipeline_token")
    rt.require(p["revision"] == state["revision"], "stale_pipeline_token")
    rt.require(p["binding_sha256"] == _binding(state), "pipeline_state_changed")
    rt.require(p["stage"] == required_stage, "pipeline_stage_required")
    _source(p["source_directory"], state)
    return p


def _move(state, stage):
    state["pipeline"]["stage"] = stage
    state["pipeline"]["revision"] = state["revision"] + 1


def _summaries(state, chapter_id):
    chunks = state["preparation"]["chunks"]
    rt.require(type(chunks) is dict, "invalid_preparation_chunks")
    return [copy.deepcopy(c) for c in chunks.values() if c["chapter_id"] == chapter_id]


def _covered(state, chapter_id, start, end):
    cursor = start
    for chunk in sorted(_summaries(state, chapter_id), key=lambda c: c["start"]):
        if chunk["end"] <= cursor:
            continue
        if chunk["start"] > cursor:
            break
        cursor = max(cursor, chunk["end"])
        if cursor >= end:
            return True
    return False


def _anchor_key(chapter_id, description):
    return rt.sha(rt.canonical([chapter_id, description]))


def _anchor_descriptions(state, chapter_id):
    return {a["description"] for chunk in _summaries(state, chapter_id) for a in chunk["anchors"]}


def _anchors_complete(state, mechanical):
    if state["anchors_disabled"] or state["cheats"]["relay"]:
        return
    chapter_id = mechanical["chapter_id"]
    ledger = mechanical.get("anchor_ledger", {})
    rt.require(all(_anchor_key(chapter_id, description) in ledger
                   for description in _anchor_descriptions(state, chapter_id)),
               "chapter_anchor_dispositions_required")


def _cards(state):
    cards = state["preparation"]["cards"]
    rt.require(type(cards) is dict and bool(cards), "confirmed_cards_required")
    return cards


def context(session, fresh=False):
    """Issue a one-use context token; fresh=True explicitly abandons a candidate."""
    rt.require(type(fresh) is bool, "invalid_fresh_context_flag")
    def operation(state):
        _ready(state)
        rt.require(state["turn"] == 0 or state["pending_action"] is not None,
                   "pending_action_required")
        rt.require(state.get("pipeline") is None or fresh, "fresh_context_required")
        require_action_budget(state)
        text = _source(session, state)
        chapter = _chapter(state)
        rt.require(_covered(state, chapter["id"], chapter["start"], chapter["end"]),
                   "current_chapter_preparation_incomplete")
        token = str(uuid.uuid4())
        state["pipeline"] = {
            "token": token, "stage": "context", "revision": state["revision"] + 1,
            "context_revision": state["revision"] + 1,
            "binding_sha256": _binding(state),
            "source_directory": str(Path(session).absolute()),
        }
        stop = min(chapter["start"] + 2000, chapter["end"])
        return {
            "token": token, "context_revision": state["revision"] + 1,
            "chapter": copy.deepcopy(chapter),
            "source": {"chapter_id": chapter["id"], "start": chapter["start"],
                       "end": stop, "text": text[chapter["start"]:stop],
                       "clipped": stop < chapter["end"],
                       "text_sha256": state["source_index"]["text_sha256"],
                       "kind": "untrusted_source_data"},
            "pending_action": copy.deepcopy(state["pending_action"]),
            "narrative_ledger": copy.deepcopy(state["world"]["narrative_ledger"][-5:]),
            "confirmed_cards": copy.deepcopy(_cards(state)),
            "accepted_distillations": _summaries(state, chapter["id"]),
            "constraints": {
                "config": copy.deepcopy(state["config"]),
                "mechanical": copy.deepcopy(state["mechanical"]),
                "anchors_disabled": state["anchors_disabled"],
                "world_facts": {k: copy.deepcopy(state["world"][k])
                                for k in ("wish_facts", "relay_facts")},
                "paper_range": list(PAPER_RANGES[state["config"]["paper_tier"]]),
                "relative_time": state["config"]["setup"]["relative_time"],
                "knowledge_caveat": "Same-chapter evidence is not permission to know future events.",
            },
            "semantic_notice": SEMANTIC_NOTICE, "next_step": "plan",
        }
    return rt.transaction(session, operation)


def _refs(refs, state, text):
    rt.require(type(refs) is list and 1 <= len(refs) <= 100, "source_reference_required")
    chapter = _chapter(state)
    triples = []
    for ref in refs:
        rt.shape(ref, ("chapter_id", "start", "end", "quote"))
        rt.require(ref["chapter_id"] == chapter["id"], "current_chapter_sources_only")
        rt.integer(ref["start"], chapter["start"], chapter["end"] - 1)
        rt.integer(ref["end"], ref["start"] + 1, chapter["end"])
        rt.string(ref["quote"], rt.MAX_TEXT)
        rt.require(text[ref["start"]:ref["end"]] == ref["quote"], "source_quote_mismatch")
        rt.require(_covered(state, ref["chapter_id"], ref["start"], ref["end"]),
                   "source_reference_not_prepared")
        triples.append((ref["chapter_id"], ref["start"], ref["end"]))
    rt.require(len(triples) == len(set(triples)), "duplicate_source_reference")


def _mortal(state):
    from engine_core.golden_finger import is_none
    name = state["config"]["gf"]["name"]
    return is_none(name) or name.strip().casefold() in ("凡人", "凡人开局", "mortal")


def plan(session, path):
    value = rt.load_json(path)
    rt.shape(value, ("token", "expected_revision", "source_refs", "intent", "outcome", "resolution",
                     "costs", "character_reactions", "ripple", "anchor", "anchor_updates", "gf_used"))
    def operation(state):
        p = _current(state, value["token"], value["expected_revision"], "context")
        require_action_budget(state)
        _refs(value["source_refs"], state, _source(session, state))
        rt.string(value["intent"])
        expected_intent = (state["pending_action"]["text"]
                           if state["pending_action"] is not None else "__opening__")
        rt.require(value["intent"] == expected_intent, "plan_intent_mismatch")
        rt.string(value["outcome"], 4000)
        rt.require(type(value["resolution"]) is str and value["resolution"] in
                   ("opening", "success", "limited", "failed"), "invalid_plan_resolution")
        rt.require(value["resolution"] != "opening" or state["turn"] == 0,
                   "opening_resolution_only_first_turn")
        costs = value["costs"]
        rt.require(type(costs) is list and 1 <= len(costs) <= 20, "plan_costs_required")
        for cost in costs:
            rt.string(cost, 1000)
        reactions = value["character_reactions"]
        rt.require(type(reactions) is list and 1 <= len(reactions) <= 100,
                   "character_reactions_required")
        names = set(_cards(state))
        seen = set()
        for reaction in reactions:
            rt.shape(reaction, ("name", "reaction"))
            rt.string(reaction["name"], 200)
            rt.require(reaction["name"] in names, "unconfirmed_reaction_character")
            rt.require(reaction["name"] not in seen, "duplicate_character_reaction")
            seen.add(reaction["name"])
            rt.string(reaction["reaction"], 2000)
        rt.require(type(value["gf_used"]) is bool, "invalid_gf_used")
        rt.require(not value["gf_used"] or not _mortal(state), "mortal_gf_forbidden")
        rt.shape(value["anchor"], ("text", "outcome"))
        rt.string(value["anchor"]["text"], empty=True)
        rt.require(type(value["anchor"]["outcome"]) is str and
                   value["anchor"]["outcome"] in mechanics.dc.OUTCOMES, "invalid_anchor_outcome")
        disabled = state["anchors_disabled"] or state["cheats"]["relay"]
        rt.require(not disabled or value["anchor"] == {"text": "", "outcome": "none"},
                   "disabled_anchor_requires_none")
        if value["anchor"]["text"]:
            rt.require(any(a["description"] == value["anchor"]["text"]
                           for chunk in _summaries(state, _chapter(state)["id"])
                           for a in chunk["anchors"]), "anchor_not_prepared")
        rt.require(value["anchor"]["outcome"] == "none" or bool(value["anchor"]["text"].strip()),
                   "anchor_text_required")
        for authored in (value["outcome"], value["costs"], value["character_reactions"],
                         value["anchor"]["text"]):
            rt.protected_data(authored)
        rt.shape(value["ripple"], ("breadth", "persistence", "canon_conflict", "pressure"))
        old = state["mechanical"]
        progress = old["chapter_turn"] / _chapter(state)["turn_budget"]
        ripple_input = {**value["ripple"], "difficulty": state["config"]["difficulty"],
                        "progress": progress, "current_total": old["ripple_total"],
                        "convergence": old["convergence"]["effective"]}
        try:
            ripple = mechanics.calculate_ripple(ripple_input)
            if disabled:
                k = None
                conv = copy.deepcopy(old["convergence"])
            else:
                protagonist = _cards(state)[state["config"]["protagonist"]["name"]]
                k = mechanics.calculate_k({"action": value["intent"],
                                          "anchor": value["anchor"]["text"],
                                          "style": protagonist["personality"]})
                conv = mechanics.calculate_convergence({"conv": old["convergence"],
                        "outcome": value["anchor"]["outcome"], "round": state["turn"] + 1})["conv"]
        except (ValueError, TypeError, OverflowError) as exc:
            raise rt.RuntimeError_("invalid_mechanical_classification") from exc
        # The resolution signal does not prove prose obeys a denied calculation.
        rt.require(ripple["allowed"] or value["resolution"] in ("limited", "failed"),
                   "denied_ripple_requires_limited_or_failed_resolution")
        proposed = copy.deepcopy(old)
        proposed["ripple_total"] += ripple["pressure"] if ripple["allowed"] else 0
        proposed["convergence"] = conv
        updates = value["anchor_updates"]
        rt.require(type(updates) is list and len(updates) <= 100, "invalid_anchor_updates")
        rt.require(not disabled or not updates, "disabled_anchor_updates_forbidden")
        descriptions = _anchor_descriptions(state, old["chapter_id"])
        update_keys = set()
        for update in updates:
            rt.shape(update, ("description", "status", "evidence"))
            rt.string(update["description"])
            rt.string(update["evidence"])
            rt.protected_data(update["evidence"])
            rt.require(update["description"] in descriptions, "anchor_not_prepared")
            rt.require(type(update["status"]) is str and update["status"] in ("fulfilled", "hint_only"),
                       "invalid_anchor_disposition")
            key = _anchor_key(old["chapter_id"], update["description"])
            rt.require(key not in update_keys, "duplicate_anchor_update")
            update_keys.add(key)
            proposed.setdefault("anchor_ledger", {})[key] = {
                "status": update["status"], "evidence": update["evidence"],
                "semantics_verified": False}
        if old["chapter_turn"] + 1 >= _chapter(state)["turn_budget"]:
            _anchors_complete(state, proposed)
        p["plan"] = copy.deepcopy(value)
        p["proposed_mechanical"] = proposed
        p["computed"] = {"ripple": ripple, "k": k, "convergence": conv,
                         "anchor_skipped": disabled,
                         "classification_inputs_unverified": True}
        _move(state, "planned")
        return {"result": "planned", "token": p["token"],
                "computed": copy.deepcopy(p["computed"]), "semantic_notice": SEMANTIC_NOTICE,
                "next_step": "stage"}
    return rt.transaction(session, operation)


def draft_sha256(draft):
    """Candidate identity excludes only per-stage transport fields."""
    return rt.sha(rt.canonical({k: v for k, v in draft.items()
                               if k not in ("expected_revision", "pipeline_token")}))


def _option_key(text):
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    # Strip a leading option label only when syntactically delimited, not 'ask'.
    text = re.sub(r"^(?:[a-f]\s*[.、:：)\]】\-]|[（(\[]\s*[a-f]\s*[）)\]])\s*", "", text)
    return "".join(c for c in text if not c.isspace()
                   and not unicodedata.category(c).startswith(("P", "Z")))


def stage(session, path):
    draft = rt.load_json(path)
    def operation(state):
        rt.require(type(draft) is dict, "object_required")
        p = _current(state, draft.get("pipeline_token"), draft.get("expected_revision"), "planned")
        rt.validate_draft(draft, state)
        rt.require(draft["source_refs"] == [
            {k: ref[k] for k in ("chapter_id", "start", "end")}
            for ref in p["plan"]["source_refs"]], "draft_source_refs_must_match_plan")
        normalized = [_option_key(option["text"]) for option in draft["options"]]
        rt.require(all(normalized) and len(set(normalized)) == 6, "distinct_options_required")
        minimum, maximum = PAPER_RANGES[state["config"]["paper_tier"]]
        rt.require(minimum <= len(draft["text"]) <= maximum, "paper_tier_length_out_of_range")
        p["draft"] = copy.deepcopy(draft)
        p["draft_sha256"] = draft_sha256(draft)
        p["story_sha256"] = rt.sha(draft["text"].encode("utf-8"))
        report = {"schema": True, "current_revision_and_token": True,
                  "exact_plan_source_ranges": True, "distinct_normalized_options": True,
                  "paper_length": {"actual": len(draft["text"]), "min": minimum, "max": maximum},
                  "semantic_verification": "not_performed", "semantic_notice": SEMANTIC_NOTICE}
        p["report"] = report
        _move(state, "staged")
        return {"result": "staged", "token": p["token"], "draft_sha256": p["draft_sha256"],
                "story_sha256": p["story_sha256"], "report": copy.deepcopy(report),
                "next_step": "review"}
    return rt.transaction(session, operation)


def review(session, path):
    value = rt.load_json(path)
    rt.shape(value, ("token", "expected_revision", "draft_sha256", "issues", "notes"))
    def operation(state):
        p = _current(state, value["token"], value["expected_revision"], "staged")
        rt.require(value["draft_sha256"] == p["draft_sha256"], "review_draft_hash_mismatch")
        rt.shape(value["notes"], REVIEW_CATEGORIES)
        for note in value["notes"].values():
            rt.string(note, 4000)
            rt.protected_data(note)
        rt.require(type(value["issues"]) is list and len(value["issues"]) <= 100,
                   "invalid_review_issues")
        for issue in value["issues"]:
            rt.shape(issue, ("category", "evidence", "start", "end"))
            rt.require(type(issue["category"]) is str and issue["category"] in REVIEW_CATEGORIES,
                       "invalid_review_category")
            rt.string(issue["evidence"], 4000)
            rt.integer(issue["start"], 0, len(p["draft"]["text"]) - 1)
            rt.integer(issue["end"], issue["start"] + 1, len(p["draft"]["text"]))
            rt.require(p["draft"]["text"][issue["start"]:issue["end"]] == issue["evidence"],
                       "review_evidence_mismatch")
        p["review"] = copy.deepcopy(value)
        rejected = bool(value["issues"])
        _move(state, "rejected" if rejected else "reviewed")
        return {"result": "review_issues_unresolved" if rejected else "reviewed",
                "token": p["token"], "draft_sha256": p["draft_sha256"],
                "semantic_notice": SEMANTIC_NOTICE,
                "next_step": "context_fresh" if rejected else "commit"}
    result = rt.transaction(session, operation)
    # Record rejection before raising: a second self-report cannot erase issues.
    if result["result"] == "review_issues_unresolved":
        raise rt.RuntimeError_("review_issues_unresolved")
    return result


def commit_ready(state, draft):
    """rt.commit hook, before any event/turn/ledger mutation; mutates only mechanics.

    Caller still validates current draft and performs narrative commit in the
    same rt.transaction. On success clears pipeline; rollback is transactional.
    """
    rt.require(type(draft) is dict, "object_required")
    p = _current(state, draft.get("pipeline_token"), draft.get("expected_revision"), "reviewed")
    rt.require(draft_sha256(draft) == p["draft_sha256"] == draft_sha256(p["draft"]),
               "committed_draft_mismatch")
    require_action_budget(state)
    state["mechanical"] = copy.deepcopy(p["proposed_mechanical"])
    state["mechanical"]["chapter_turn"] += 1
    state["mechanical"]["last_computed"] = copy.deepcopy(p["computed"])
    state["last_turn_audit"] = {k: copy.deepcopy(p[k]) for k in
                                ("plan", "computed", "report", "review", "draft_sha256", "story_sha256")}
    state["last_turn_audit"]["semantic_notice"] = SEMANTIC_NOTICE
    state["pipeline"] = None


def render(session):
    """Read-only: never expose uncommitted text or regenerate prose."""
    with rt.locked(session) as directory:
        state, _ = rt.load_session(directory)
        _ready(state)
        event = next((e for e in reversed(state["events"]) if e.get("type") == "narrative"), None)
        rt.require(event is not None, "no_committed_narrative")
        return {"text": event["text"], "options": copy.deepcopy(event["options"]),
                "summary": event["summary"], "turn": event["turn"],
                "revision": state["revision"], "mechanical": copy.deepcopy(state["mechanical"]),
                "semantic_notice": SEMANTIC_NOTICE}


def advance(session, text):
    rt.require(text == "确认翻章", "exact_chapter_confirmation_required")
    def operation(state):
        _ready(state)
        rt.require(state["pending_action"] is None, "pending_action_blocks_advance")
        chapter = _chapter(state)
        rt.require(state["mechanical"]["chapter_turn"] >= chapter["turn_budget"],
                   "chapter_budget_not_exhausted")
        _anchors_complete(state, state["mechanical"])
        chapters = state["source_index"]["chapters"]
        position = next(i for i, c in enumerate(chapters) if c["id"] == chapter["id"])
        rt.require(position + 1 < len(chapters), "no_next_chapter")
        following = chapters[position + 1]
        _source(session, state)
        rt.require(_covered(state, following["id"], following["start"], following["end"]),
                   "next_chapter_preparation_incomplete")
        state["mechanical"]["chapter_id"] = following["id"]
        state["mechanical"]["chapter_turn"] = 0
        state["pipeline"] = None
        state["events"].append({"type": "chapter_advanced", "from": chapter["id"],
                                "to": following["id"], "turn": state["turn"]})
        return {"result": "chapter_advanced", "chapter": copy.deepcopy(following),
                "next_step": "action", "narrative_generated": False}
    return rt.transaction(session, operation)
