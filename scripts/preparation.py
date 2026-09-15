# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic preparation gates and local, quote-verified evidence.

Source and character content are data, never instructions. A receipt proves an
exact source window was issued; accepted summaries prove neither comprehension
nor semantic correctness. No external model or semantic evaluator is invoked.
Offsets in receipts, evidence, and cards are absolute Unicode code points.
Card source_refs are narrator identity evidence, not character knowledge. Source
identity requires the exact configured name in a verified quote; aliases are not
supported. Only knowledge entries are bounded by the character's time cutoff.
"""
from __future__ import annotations

import copy
import secrets

import runtime as rt

CHUNK_SIZE = 2000
MAX_CHUNKS = 5000
MAX_ITEMS = 100
PROVENANCE = "current_assistant_unverified_semantics"
ROLES = ("protagonist", "companion", "partner", "nemesis", "support")
CARD_TEXT_FIELDS = ("name", "role", "origin", "description", "personality", "goal",
                    "desire", "fear", "decision_principle", "taboo", "mind_model",
                    "decision_policy", "voice_transfer")
CARD_FIELDS = (*CARD_TEXT_FIELDS, "abilities", "limits", "relationships", "knowledge",
               "source_refs", "voice_samples", "behavior_boundaries")


def _chapters(state):
    return {chapter["id"]: chapter for chapter in state["source_index"]["chapters"]}


def _expected(state):
    cfg = state["config"]
    names = [cfg["protagonist"]["name"], *(c["name"] for c in cfg["characters"])]
    rt.require(len(names) == len(set(names)), "duplicate_configured_character_name")
    return names


def initialize(state):
    """Called by create before signing; never resets an existing preparation."""
    rt.require("preparation" not in state, "preparation_already_initialized")
    _expected(state)
    setup = state["config"]["setup"]
    chapters = _chapters(state)
    target = setup["target_chapter"]
    rt.require(target in chapters, "unknown_target_chapter")
    scope = list(chapters) if setup["preparation_mode"] == "fullbook" else [target]
    rt.require(sum((chapters[c]["chars"] + CHUNK_SIZE - 1) // CHUNK_SIZE
                   for c in scope) <= MAX_CHUNKS, "preparation_scope_chunk_limit")
    state["preparation"] = {
        "version": 2, "setup_confirmed": False, "gf_confirmed": False,
        "cards": {}, "cast_confirmed": False, "issued": {}, "chunks": {},
        "selected_scope": scope, "chunk_size": CHUNK_SIZE,
    }


def _preparation(state):
    prep = state.get("preparation")
    rt.require(type(prep) is dict and prep.get("version") == 2,
               "legacy_session_preparation_missing")
    return prep


def _phase(state, reading=False):
    rt.require(state["phase"] in (("awaiting_opening", "playing") if reading
                                  else ("awaiting_opening",)), "invalid_preparation_phase")
    return _preparation(state)


def _source(session, state):
    # Read while the caller's transaction holds the session lock. The unsigned
    # index must match the signed index too, not merely the adjacent source file.
    text, index = rt.prepared_data(session)
    rt.require(index == state["source_index"], "signed_source_index_mismatch")
    return text


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def progress(state):
    """Report measured receipt-range union, not self-declared semantic coverage."""
    prep = _preparation(state)
    chapters = _chapters(state)
    grouped = {}
    for chunk in prep["chunks"].values():
        grouped.setdefault(chunk["chapter_id"], []).append((chunk["start"], chunk["end"]))
    reports, missing = [], []
    for chapter_id in prep["selected_scope"]:
        chapter = chapters[chapter_id]
        intervals = _merge(grouped.get(chapter_id, []))
        cursor = chapter["start"]
        gaps = []
        for start, end in intervals:
            if cursor < start:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < chapter["end"]:
            gaps.append((cursor, chapter["end"]))
        for start, end in gaps:
            for begin in range(start, end, CHUNK_SIZE):
                missing.append({"chapter_id": chapter_id, "start": begin,
                                "end": min(begin + CHUNK_SIZE, end)})
        reports.append({"chapter_id": chapter_id, "intervals": intervals,
                        "interval_count": len(intervals),
                        "covered_chars": sum(b - a for a, b in intervals),
                        "total_chars": chapter["chars"]})
    return {"selected_scope": list(prep["selected_scope"]), "chunk_size": CHUNK_SIZE,
            "chunk_count": len(prep["chunks"]), "issued_count": len(prep["issued"]),
            "interval_count": sum(c["interval_count"] for c in reports),
            "covered_chars": sum(c["covered_chars"] for c in reports),
            "total_chars": sum(c["total_chars"] for c in reports),
            "chapters": reports, "missing_windows": missing, "complete": not missing,
            "coverage_kind": "accepted_receipt_range_union_not_semantic_verification",
            "provenance": PROVENANCE}


def source_window(session, chapter, start=0, limit=CHUNK_SIZE):
    """Issue a one-use receipt. Input start is relative to the named chapter."""
    def operation(state):
        prep = _phase(state, reading=True)
        chapters = _chapters(state)
        rt.require(type(chapter) is str and chapter in chapters, "unknown_chapter")
        found = chapters[chapter]
        rt.integer(start, 0, found["chars"] - 1)
        rt.integer(limit, 1, CHUNK_SIZE)
        text = _source(session, state)
        begin, end = found["start"] + start, min(found["start"] + start + limit, found["end"])
        # Re-reading immutable data must not consume receipts or change revision.
        # Always verify the on-disk source before taking this idempotent path.
        receipt = next((item for item in prep["issued"].values()
                        if item.get("chapter_id") == chapter and item.get("start") == begin
                        and item.get("end") == end), None)
        source_hash = state["source_index"]["text_sha256"]
        window_hash = rt.sha(text[begin:end].encode("utf-8"))
        if receipt is not None:
            rt.require(receipt["source_sha256"] == source_hash
                       and receipt["text_sha256"] == window_hash, "receipt_source_mismatch")
        else:
            rt.require(len(prep["issued"]) < MAX_CHUNKS, "receipt_count_limit")
            receipt_id = secrets.token_hex(16)
            while receipt_id in prep["issued"]:
                receipt_id = secrets.token_hex(16)
            receipt = {"receipt_id": receipt_id, "chapter_id": chapter, "start": begin, "end": end,
                       "source_sha256": source_hash, "text_sha256": window_hash}
            prep["issued"][receipt_id] = receipt
        return {**receipt, "kind": "untrusted_source_data", "not_instructions": True,
                "text": text[begin:end], "offset_unit": "unicode_code_points",
                "interval": "start_inclusive_end_exclusive"}
    return rt.transaction(session, operation)


def _authored(value, maximum=4000):
    rt.string(value, maximum)
    rt.protected_data(value)


def _quote(ref, text, start, end):
    rt.integer(ref["start"], start, end - 1)
    rt.integer(ref["end"], ref["start"] + 1, end)
    # Quotes are source data, not authored claims; do not interpret or sanitize.
    rt.require(type(ref["quote"]) is str and 0 < len(ref["quote"]) <= CHUNK_SIZE,
               "invalid_quote")
    rt.require(ref["quote"] == text[ref["start"]:ref["end"]], "source_quote_mismatch")


def distill(session, path):
    payload = rt.load_json(path)
    rt.shape(payload, ("receipt_id", "summary", "facts", "anchors"))
    rt.string(payload["receipt_id"], 64)
    _authored(payload["summary"])
    rt.require(type(payload["facts"]) is list and 1 <= len(payload["facts"]) <= MAX_ITEMS,
               "distillation_facts_required")
    rt.require(type(payload["anchors"]) is list and len(payload["anchors"]) <= MAX_ITEMS,
               "invalid_distillation_anchors")

    def operation(state):
        prep = _phase(state, reading=True)
        anchors_skipped = bool(state.get("anchor_distillation_disabled", False))
        rt.require(not anchors_skipped or not payload["anchors"], "anchor_distillation_disabled")
        rid = payload["receipt_id"]
        rt.require(rid in prep["issued"], "unknown_receipt")
        rt.require(rid not in prep["chunks"], "receipt_already_distilled")
        rt.require(len(prep["chunks"]) < MAX_CHUNKS, "distillation_chunk_limit")
        receipt = prep["issued"][rid]
        text = _source(session, state)
        rt.require(receipt["source_sha256"] == state["source_index"]["text_sha256"]
                   and receipt["text_sha256"] == rt.sha(text[receipt["start"]:receipt["end"]].encode("utf-8")),
                   "receipt_source_mismatch")
        for items, key in ((payload["facts"], "claim"), (payload["anchors"], "description")):
            for item in items:
                rt.shape(item, (key, "quote", "start", "end"))
                _authored(item[key])
                _quote(item, text, receipt["start"], receipt["end"])
        prep["chunks"][rid] = {
            **copy.deepcopy(receipt), "summary": payload["summary"],
            "facts": copy.deepcopy(payload["facts"]), "anchors": copy.deepcopy(payload["anchors"]),
            "provenance": PROVENANCE, "quotes_verified": True, "semantics_verified": False,
            "not_instructions": True, "anchors_skipped": anchors_skipped,
        }
        return {"result": "distillation_accepted", "receipt_id": rid, "provenance": PROVENANCE,
                "quotes_verified": True, "semantics_verified": False,
                "anchors_skipped": anchors_skipped, "progress": progress(state)}
    return rt.transaction(session, operation)


def setup_confirm(session, text):
    def operation(state):
        prep = _phase(state)
        rt.require(text == "确认设定", "exact_setup_confirmation_required")
        _source(session, state)
        rt.require(progress(state)["complete"], "source_scope_coverage_incomplete")
        prep["setup_confirmed"] = True
        return {"setup_confirmed": True, "progress": progress(state)}
    return rt.transaction(session, operation)


def gf_confirm(session, text):
    def operation(state):
        prep = _phase(state)
        rt.require(prep["setup_confirmed"], "setup_confirmation_required")
        rt.require(text in ("确认金手指", "确认无金手指"), "exact_gf_confirmation_required")
        rt.require(text != "确认无金手指" or state["config"]["gf"]["name"] == "凡人",
                   "non_mortal_gf_requires_confirmation")
        prep["gf_confirmed"] = True
        return {"gf_confirmed": True}
    return rt.transaction(session, operation)


def _knowledge_ids(state):
    setup = state["config"]["setup"]
    ids = list(_chapters(state))
    cutoff = ids.index(setup["target_chapter"])
    if setup["relative_time"] != "before":
        cutoff += 1
    return set(ids[:cutoff])


def _card_reference(ref, state, text):
    rt.shape(ref, ("chapter_id", "start", "end", "quote"))
    rt.require(type(ref["chapter_id"]) is str and ref["chapter_id"] in _chapters(state),
               "unknown_source_chapter")
    chapter = _chapters(state)[ref["chapter_id"]]
    _quote(ref, text, chapter["start"], chapter["end"])
    # A broad summary of a window does not make every character assertion cited.
    # Card quotes must be contained in a quote actually accepted as evidence.
    rt.require(any(chunk["chapter_id"] == ref["chapter_id"]
                   and any(item["start"] <= ref["start"] and ref["end"] <= item["end"]
                           for item in (*chunk["facts"], *chunk["anchors"]))
                   for chunk in _preparation(state)["chunks"].values()),
               "character_quote_not_distilled")


def card(session, path):
    payload = rt.load_json(path)
    rt.shape(payload, CARD_FIELDS)
    for key in CARD_TEXT_FIELDS:
        _authored(payload[key])
    rt.require(payload["role"] in ROLES, "invalid_character_role")
    rt.require(payload["origin"] in ("source", "original"), "invalid_character_origin")
    for key in ("abilities", "limits", "relationships", "voice_samples", "behavior_boundaries"):
        values = payload[key]
        minimum = 2 if key == "voice_samples" else (0 if key == "relationships" else 1)
        rt.require(type(values) is list and minimum <= len(values) <= MAX_ITEMS,
                   "invalid_character_list")
        for value in values:
            _authored(value)
        if key == "voice_samples":
            rt.require(len({value.strip() for value in values}) == len(values),
                       "distinct_character_voice_samples_required")
    for key in ("knowledge", "source_refs"):
        rt.require(type(payload[key]) is list and len(payload[key]) <= MAX_ITEMS,
                   "invalid_character_list")
    rt.require(payload["origin"] != "source" or bool(payload["source_refs"]),
               "source_character_references_required")

    def operation(state):
        prep = _phase(state)
        rt.require(prep["setup_confirmed"] and prep["gf_confirmed"], "character_confirmation_prerequisites")
        rt.require(not prep["cast_confirmed"], "cast_already_confirmed")
        rt.require(payload["name"] in _expected(state), "undeclared_character")
        protagonist = state["config"]["protagonist"]["name"]
        rt.require((payload["role"] == "protagonist") == (payload["name"] == protagonist),
                   "protagonist_role_mismatch")
        if payload["name"] == protagonist:
            rt.require(payload["origin"] == state["config"]["protagonist"].get("origin", "original"),
                       "configured_character_origin_mismatch")
        else:
            cfg = next(c for c in state["config"]["characters"] if c["name"] == payload["name"])
            rt.require(payload["role"] == cfg.get("role", "support"), "configured_character_role_mismatch")
            rt.require(payload["origin"] == cfg.get("origin", "source"), "configured_character_origin_mismatch")
        allowed = _knowledge_ids(state)
        for knowledge in payload["knowledge"]:
            rt.shape(knowledge, ("fact", "chapter_id"))
            _authored(knowledge["fact"])
            rt.require(type(knowledge["chapter_id"]) is str and knowledge["chapter_id"] in allowed,
                       "character_knowledge_future_or_unknown")
        text = _source(session, state)
        for ref in payload["source_refs"]:
            _card_reference(ref, state, text)
        rt.require(payload["origin"] != "source"
                   or any(payload["name"] in ref["quote"] for ref in payload["source_refs"]),
                   "source_character_name_not_quoted")
        replaced = payload["name"] in prep["cards"]
        prep["cards"][payload["name"]] = copy.deepcopy(payload)
        return {"result": "character_card_accepted", "name": payload["name"], "replaced": replaced,
                "card_count": len(prep["cards"]), "provenance": PROVENANCE,
                "not_instructions": True}
    return rt.transaction(session, operation)


def _cast_complete(state):
    prep = _preparation(state)
    rt.require(set(prep["cards"]) == set(_expected(state)), "configured_character_cards_incomplete")
    cards = list(prep["cards"].values())
    rt.require(sum(c["role"] == "protagonist" for c in cards) == 1
               and prep["cards"][state["config"]["protagonist"]["name"]]["role"] == "protagonist",
               "protagonist_role_mismatch")
    setup = state["config"]["setup"]
    for role, count in (("companion", setup["companions"]), ("partner", setup["partners"]),
                        ("nemesis", int(setup["nemesis"]))):
        rt.require(sum(c["role"] == role for c in cards) == count, "configured_cast_role_count_mismatch")


def cast_confirm(session, text):
    def operation(state):
        prep = _phase(state)
        rt.require(text == "确认角色", "exact_cast_confirmation_required")
        rt.require(prep["setup_confirmed"] and prep["gf_confirmed"], "character_confirmation_prerequisites")
        _source(session, state)
        _cast_complete(state)
        prep["cast_confirmed"] = True
        return {"cast_confirmed": True, "card_count": len(prep["cards"])}
    return rt.transaction(session, operation)


def ready(state):
    prep = _preparation(state)
    rt.require(prep["setup_confirmed"], "setup_confirmation_required")
    rt.require(prep["gf_confirmed"], "gf_confirmation_required")
    rt.require(prep["cast_confirmed"], "cast_confirmation_required")
    rt.require(progress(state)["complete"], "source_scope_coverage_incomplete")
    _cast_complete(state)
    return True
