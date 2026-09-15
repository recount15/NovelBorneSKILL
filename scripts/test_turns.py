# SPDX-License-Identifier: AGPL-3.0-or-later
"""Targeted turn pipeline tests, using real preparation and signed sessions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import mechanics
import preparation
import runtime as rt
import turns


class TurnsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="novelborne-turns-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.book = "第一章 雨城\n林走进雨城。陈站在屋檐下。\n第二章 河边\n陈来到河边，林看见小船。"
        source = self.base / "source.txt"
        source.write_bytes(self.book.encode("utf-8"))
        prepared = self.base / "prepared"
        rt.prepare(source, prepared)
        config = {
            "mode": "基础模式", "difficulty": 3, "convergence": "一般", "paper_tier": 2,
            "protagonist": {"name": "林", "description": "谨慎的旅人"},
            "source": {"title": "雨城", "description": "本地试验文本"},
            "characters": [{"name": "陈", "description": "屋檐下的人"}],
            "gf": {"name": "凡人", "effect": "无超凡能力", "scope": "自身", "cost": "无",
                   "cooldown": "不适用", "limits": "凡人能力边界"},
        }
        self.session = Path(rt.create(self.base / "sessions", self.dump(config), prepared)["session"])
        self.prepare_chapter("ch0001")
        preparation.setup_confirm(self.session, "确认设定")
        preparation.gf_confirm(self.session, "确认无金手指")
        chapter = self.state()["source_index"]["chapters"][0]
        for name in ("林", "陈"):
            card = {
                "name": name, "role": "protagonist" if name == "林" else "support",
                "origin": "original" if name == "林" else "source",
                "description": "雨中的行人", "personality": "苟稳型", "goal": "寻找避雨之处",
                "abilities": ["步行"], "limits": ["怕冷"], "relationships": [], "knowledge": [],
                "source_refs": [] if name == "林" else [{"chapter_id": chapter["id"],
                    "start": chapter["start"], "end": chapter["end"],
                    "quote": self.book[chapter["start"]:chapter["end"]]}],
                "desire": "找到落脚点", "fear": "失去住所", "decision_principle": "先观察再行动",
                "taboo": "不欺负弱者", "voice_samples": ["雨还会下很久。", "先到屋檐下去。"],
                "behavior_boundaries": ["不主动动手"], "mind_model": "关注眼前环境",
                "decision_policy": "避免无谓争执", "voice_transfer": "语气平静简短",
            }
            preparation.card(self.session, self.dump(card))
        preparation.cast_confirm(self.session, "确认角色")
        rt.confirm(self.session, "确认开局")

    def dump(self, value):
        path = self.base / "input.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def state(self):
        with rt.locked(self.session) as directory:
            return rt.load_session(directory)[0]

    def prepare_chapter(self, chapter_id):
        receipt = preparation.source_window(self.session, chapter_id)
        preparation.distill(self.session, self.dump({
            "receipt_id": receipt["receipt_id"], "summary": "雨中的行人观察周围。",
            "facts": [{"claim": "人物出现在当前地点", "quote": receipt["text"],
                       "start": receipt["start"], "end": receipt["end"]}],
            "anchors": [{"description": "行人来到雨城" if chapter_id == "ch0001" else "行人来到河边",
                         "quote": receipt["text"], "start": receipt["start"], "end": receipt["end"]}],
        }))

    def plan_value(self):
        state = self.state()
        chapter = next(c for c in state["source_index"]["chapters"]
                       if c["id"] == state["mechanical"]["chapter_id"])
        return {"token": state["pipeline"]["token"], "expected_revision": state["revision"],
                "source_refs": [{"chapter_id": chapter["id"], "start": chapter["start"],
                                 "end": chapter["end"], "quote": self.book[chapter["start"]:chapter["end"]]}],
                "intent": state["pending_action"]["text"] if state["pending_action"] else "__opening__",
                "outcome": "旅人观察雨势，找到屋檐。", "resolution": "opening" if not state["turn"] else "success",
                "costs": ["衣服被雨打湿"], "character_reactions": [{"name": "陈", "reaction": "抬头看看行人"}],
                "ripple": {"breadth": 1, "persistence": 1, "canon_conflict": 0, "pressure": 1},
                "anchor": {"text": "", "outcome": "none"}, "anchor_updates": [], "gf_used": False}

    def draft_value(self):
        state = self.state()
        p = state["pipeline"]
        target = turns.PAPER_TARGETS[state["config"]["paper_tier"] - 1]
        return {"expected_revision": state["revision"], "pipeline_token": p["token"],
                "text": ("雨水沿着屋檐滴落，旅人站在石阶旁观察街道。" * target)[:target],
                "summary": "旅人在街旁避雨。",
                "options": [{"id": ident, "text": text, "kind": "plot" if i < 4 else "personality"}
                            for i, (ident, text) in enumerate(zip("ABCDEF", (
                                "向陈问路", "站到屋檐下", "看看街上的脚印", "寻找客店", "先整理衣衫", "轻声哼歌")))],
                "source_refs": [{k: r[k] for k in ("chapter_id", "start", "end")}
                                for r in p["plan"]["source_refs"]], "world_updates": ["旅人来到屋檐下"]}

    def review_value(self):
        state = self.state()
        return {"token": state["pipeline"]["token"], "expected_revision": state["revision"],
                "draft_sha256": state["pipeline"]["draft_sha256"], "issues": [],
                "notes": {k: "正文只描写雨水和屋檐，没有增加人物所知的秘密。"
                          for k in turns.REVIEW_CATEGORIES}}

    def pending(self):
        path = self.base / "action.txt"
        path.write_text("A", encoding="utf-8")
        return rt.action(self.session, path)

    def through_stage(self):
        turns.context(self.session)
        plan = self.plan_value()
        state = self.state()
        chapter = turns._chapter(state)
        if state["mechanical"]["chapter_turn"] + 1 == chapter["turn_budget"]:
            plan["anchor_updates"] = [{"description": description, "status": "fulfilled",
                                       "evidence": "正文中的旅人已经来到所述地点。"}
                                      for description in turns._anchor_descriptions(state, chapter["id"])]
        turns.plan(self.session, self.dump(plan))
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        return draft

    def commit_candidate(self, draft):
        draft = copy.deepcopy(draft)
        draft["expected_revision"] = self.state()["revision"]
        return rt.commit(self.session, self.dump(draft))

    def complete(self):
        draft = self.through_stage()
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        return draft

    def unchanged_failure(self, call, pattern=None):
        before = (self.session / "state.json").read_bytes()
        with self.assertRaisesRegex(rt.RuntimeError_, pattern or ".+"):
            call()
        self.assertEqual(before, (self.session / "state.json").read_bytes())

    def test_initial_mechanics_and_context_revision(self):
        state = self.state()
        self.assertIsNone(state["pipeline"])
        self.assertEqual(state["mechanical"]["ripple_total"], 0)
        self.assertEqual(state["mechanical"]["convergence"], mechanics.calculate_convergence({"base": "一般"})["conv"])
        result = turns.context(self.session)
        self.assertEqual(result["revision"], result["context_revision"])
        self.assertEqual(result["source"]["text"], self.book[:self.book.index("第二章")])
        self.assertEqual(set(result["confirmed_cards"]), {"林", "陈"})
        self.assertEqual(len(result["accepted_distillations"]), 1)
        self.assertEqual(result["next_step"], "plan")

    def test_pipeline_commits_only_reviewed_exact_candidate(self):
        self.unchanged_failure(lambda: turns.render(self.session), "no_committed")
        draft = self.through_stage()
        self.assertEqual(self.state()["mechanical"]["ripple_total"], 0)
        self.unchanged_failure(lambda: self.commit_candidate(draft), "pipeline_stage")
        turns.review(self.session, self.dump(self.review_value()))
        changed = copy.deepcopy(draft)
        changed["summary"] = "不同的摘要"
        self.unchanged_failure(lambda: self.commit_candidate(changed), "committed_draft_mismatch")
        self.commit_candidate(draft)
        state = self.state()
        self.assertIsNone(state["pipeline"])
        self.assertEqual(state["mechanical"]["chapter_turn"], 1)
        self.assertEqual(state["mechanical"]["ripple_total"], 1)
        self.assertEqual(state["turn"], 1)
        before = (self.session / "state.json").read_bytes()
        result = turns.render(self.session)
        self.assertEqual(result["text"], draft["text"])
        self.assertEqual(result["options"], draft["options"])
        self.assertEqual(result["summary"], draft["summary"])
        self.assertEqual(before, (self.session / "state.json").read_bytes())
        self.assertIn("review", state["last_turn_audit"])
        self.unchanged_failure(lambda: self.commit_candidate(draft))

    def test_context_requires_pending_and_explicit_reset(self):
        draft = self.through_stage()
        old_token = draft["pipeline_token"]
        self.unchanged_failure(lambda: turns.context(self.session), "fresh_context")
        turns.context(self.session, fresh=True)
        self.assertNotEqual(self.state()["pipeline"]["token"], old_token)
        self.assertNotIn("draft", self.state()["pipeline"])
        self.unchanged_failure(lambda: turns.stage(self.session, self.dump(draft)))
        turns.plan(self.session, self.dump(self.plan_value()))
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        self.unchanged_failure(lambda: turns.context(self.session), "pending_action")
        self.pending()
        result = turns.context(self.session)
        self.assertEqual(result["pending_action"]["text"], "A")

    def test_stale_revision_and_preparation_changes_invalidate_token(self):
        turns.context(self.session)
        plan = self.plan_value()
        self.prepare_chapter("ch0002")
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "stale_revision")
        plan["expected_revision"] = self.state()["revision"]
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "stale_pipeline")

    def test_reviewed_token_invalid_after_cheat_state_change(self):
        draft = self.through_stage()
        turns.review(self.session, self.dump(self.review_value()))
        # Programmatic constant use; no opaque code is printed or persisted in fixtures.
        path = self.base / "question.txt"
        path.write_text(rt.WISH_CODE, encoding="utf-8")
        rt.ask(self.session, path)
        self.unchanged_failure(lambda: self.commit_candidate(draft), "stale_pipeline")

    def test_source_integrity_detects_source_and_unsigned_index_replacement(self):
        turns.context(self.session)
        plan = self.plan_value()
        source = self.session / "source.txt"
        original = source.read_bytes()
        source.write_bytes(original + b"changed")
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "integrity")
        source.write_bytes(original)
        index_path = self.session / "index.json"
        index = rt.load_json(index_path)
        index["chapters"][0]["title"] = "伪造标题"
        index_path.write_bytes(rt.canonical(index))
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "signed_source_index")

    def test_plan_validates_exact_schema_quotes_intent_cards_costs_and_gf(self):
        turns.context(self.session)
        good = self.plan_value()
        mutations = [lambda v: v.update(extra=True), lambda v: v.update(intent="不同的行动"),
                     lambda v: v.update(costs=[]), lambda v: v.update(gf_used=True),
                     lambda v: v["character_reactions"][0].update(name="陌生人"),
                     lambda v: v["source_refs"][0].update(quote="不匹配"),
                     lambda v: v["source_refs"][0].update(chapter_id="ch0002"),
                     lambda v: v["ripple"].update(pressure=True),
                     lambda v: v["anchor"].update(outcome="unknown"),
                     lambda v: v.update(resolution="unknown"),
                     lambda v: v["anchor"].update(text="捏造事件", outcome="offset")]
        for mutation in mutations:
            value = copy.deepcopy(good)
            mutation(value)
            self.unchanged_failure(lambda v=value: turns.plan(self.session, self.dump(v)))
        turns.plan(self.session, self.dump(good))

    def test_accepted_anchor_settles_convergence(self):
        turns.context(self.session)
        plan = self.plan_value()
        plan["anchor"] = {"text": "行人来到雨城", "outcome": "offset"}
        before = copy.deepcopy(self.state()["mechanical"]["convergence"])
        turns.plan(self.session, self.dump(plan))
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        expected = mechanics.calculate_convergence({"conv": before, "outcome": "offset", "round": 1})["conv"]
        self.assertEqual(self.state()["mechanical"]["convergence"], expected)

    def test_denied_ripple_never_accumulates(self):
        turns.context(self.session)
        plan = self.plan_value()
        plan["ripple"] = {"breadth": 4, "persistence": 4, "canon_conflict": 4, "pressure": 3}
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "denied_ripple")
        plan["resolution"] = "limited"
        result = turns.plan(self.session, self.dump(plan))
        self.assertFalse(result["computed"]["ripple"]["allowed"])
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        self.assertEqual(self.state()["mechanical"]["ripple_total"], 0)

    def test_draft_requires_matching_ranges_unique_options_and_paper_bounds(self):
        turns.context(self.session)
        turns.plan(self.session, self.dump(self.plan_value()))
        good = self.draft_value()
        low, high = turns.PAPER_RANGES[2]
        variants = []
        for length in (low - 1, high + 1):
            bad = copy.deepcopy(good)
            bad["text"] = "雨" * length
            variants.append(bad)
        bad = copy.deepcopy(good)
        bad["source_refs"][0]["end"] -= 1
        variants.append(bad)
        bad = copy.deepcopy(good)
        bad["options"][0]["text"] = "A. 问 路！"
        bad["options"][1]["text"] = "B：问路。"
        variants.append(bad)
        for value in variants:
            self.unchanged_failure(lambda v=value: turns.stage(self.session, self.dump(v)))
        good["text"] = "雨" * low
        turns.stage(self.session, self.dump(good))
        turns.context(self.session, fresh=True)
        turns.plan(self.session, self.dump(self.plan_value()))
        good = self.draft_value()
        good["text"] = "雨" * high
        turns.stage(self.session, self.dump(good))

    def test_review_schema_evidence_and_rejection_requires_new_context(self):
        draft = self.through_stage()
        good = self.review_value()
        invalid = copy.deepcopy(good)
        invalid["notes"]["knowledge"] = True
        self.unchanged_failure(lambda: turns.review(self.session, self.dump(invalid)))
        invalid = copy.deepcopy(good)
        invalid["issues"] = [{"category": "knowledge", "start": 0, "end": 2, "evidence": "错误"}]
        self.unchanged_failure(lambda: turns.review(self.session, self.dump(invalid)), "evidence")
        good["issues"] = [{"category": "causality", "start": 0, "end": 2,
                           "evidence": draft["text"][:2]}]
        with self.assertRaisesRegex(rt.RuntimeError_, "review_issues_unresolved"):
            turns.review(self.session, self.dump(good))
        self.assertEqual(self.state()["pipeline"]["stage"], "rejected")
        good = self.review_value()
        self.unchanged_failure(lambda: turns.review(self.session, self.dump(good)), "pipeline_stage")
        self.unchanged_failure(lambda: self.commit_candidate(draft))
        turns.context(self.session, fresh=True)
        self.assertEqual(self.state()["pipeline"]["stage"], "context")

    def test_relay_skips_anchor_and_convergence(self):
        path = self.base / "question.txt"
        path.write_text(rt.RELAY_CODE, encoding="utf-8")
        rt.ask(self.session, path)
        path.write_text("确认", encoding="utf-8")
        rt.ask(self.session, path)
        before = self.state()["mechanical"]["convergence"]
        turns.context(self.session)
        plan = self.plan_value()
        plan["anchor"] = {"text": "行人来到雨城", "outcome": "offset"}
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(plan)), "disabled_anchor")
        plan["anchor"] = {"text": "", "outcome": "none"}
        result = turns.plan(self.session, self.dump(plan))
        self.assertIsNone(result["computed"]["k"])
        self.assertTrue(result["computed"]["anchor_skipped"])
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        self.assertEqual(self.state()["mechanical"]["convergence"], before)

    def test_budget_advance_and_no_automatic_narrative(self):
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章 "), "exact_chapter")
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章"), "not_exhausted")
        budget = self.state()["source_index"]["chapters"][0]["turn_budget"]
        for i in range(budget):
            if i:
                self.pending()
            self.complete()
        self.unchanged_failure(self.pending, "budget_exhausted")
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章"), "preparation_incomplete")
        self.prepare_chapter("ch0002")
        before = turns.render(self.session)
        result = turns.advance(self.session, "确认翻章")
        self.assertFalse(result["narrative_generated"])
        self.assertEqual(self.state()["mechanical"]["chapter_turn"], 0)
        self.assertEqual(self.state()["mechanical"]["chapter_id"], "ch0002")
        self.assertEqual(turns.render(self.session)["text"], before["text"])
        self.unchanged_failure(lambda: turns.context(self.session), "pending_action")
        self.pending()
        context = turns.context(self.session)
        self.assertEqual(context["chapter"]["id"], "ch0002")
        self.assertEqual(context["source"]["text"], self.book[self.book.index("第二章"):])

    def test_final_turn_requires_anchor_disposition_and_persists_only_at_commit(self):
        self.complete()
        self.pending()
        self.complete()
        self.pending()
        turns.context(self.session)
        value = self.plan_value()
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(value)),
                               "anchor_dispositions_required")
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章"),
                               "pending_action_blocks")
        for status in ("shattered", "success", True):
            value["anchor_updates"] = [{"description": "行人来到雨城", "status": status,
                                         "evidence": "旅人抵达屋檐下。"}]
            self.unchanged_failure(lambda: turns.plan(self.session, self.dump(value)),
                                   "invalid_anchor_disposition")
        value["anchor_updates"][0]["status"] = "fulfilled"
        turns.plan(self.session, self.dump(value))
        self.assertEqual(self.state()["mechanical"]["anchor_ledger"], {})
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        ledger = self.state()["mechanical"]["anchor_ledger"]
        self.assertEqual(len(ledger), 1)
        self.assertEqual(next(iter(ledger.values()))["status"], "fulfilled")
        self.assertFalse(next(iter(ledger.values()))["semantics_verified"])

    def test_plan_stage_and_review_cannot_be_skipped_or_replayed(self):
        turns.context(self.session)
        value = self.plan_value()
        turns.plan(self.session, self.dump(value))
        value["expected_revision"] = self.state()["revision"]
        self.unchanged_failure(lambda: turns.plan(self.session, self.dump(value)), "pipeline_stage")
        draft = self.draft_value()
        self.unchanged_failure(lambda: self.commit_candidate(draft), "pipeline_stage")
        turns.stage(self.session, self.dump(draft))
        draft["expected_revision"] = self.state()["revision"]
        self.unchanged_failure(lambda: turns.stage(self.session, self.dump(draft)), "pipeline_stage")
        review = self.review_value()
        review["draft_sha256"] = "0" * 64
        self.unchanged_failure(lambda: turns.review(self.session, self.dump(review)), "hash_mismatch")
        review = self.review_value()
        turns.review(self.session, self.dump(review))
        review["expected_revision"] = self.state()["revision"]
        self.unchanged_failure(lambda: turns.review(self.session, self.dump(review)), "pipeline_stage")

    def test_context_ledger_window_and_end_of_book_gate(self):
        for i in range(3):
            if i:
                self.pending()
            self.complete()
        self.prepare_chapter("ch0002")
        turns.advance(self.session, "确认翻章")
        for _ in range(2):
            self.pending()
            self.complete()
        self.pending()
        result = turns.context(self.session)
        self.assertEqual([item["turn"] for item in result["narrative_ledger"]], [1, 2, 3, 4, 5])
        value = self.plan_value()
        value["anchor_updates"] = [{"description": "行人来到河边", "status": "hint_only",
                                    "evidence": "当前地点已经呈现，但不替人物决定行动。"}]
        turns.plan(self.session, self.dump(value))
        draft = self.draft_value()
        turns.stage(self.session, self.dump(draft))
        turns.review(self.session, self.dump(self.review_value()))
        self.commit_candidate(draft)
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章"), "no_next_chapter")

    def test_legacy_turn_functions_reject_without_mutation(self):
        # A signed legacy snapshot models an existing v1 save, not a gate bypass.
        with rt.locked(self.session) as directory:
            state, key = rt.load_session(directory)
            state["version"] = 1
            rt.atomic_state(directory, state, key)
        self.unchanged_failure(lambda: turns.context(self.session), "legacy|v2")
        self.unchanged_failure(lambda: turns.advance(self.session, "确认翻章"), "legacy|v2")
        self.unchanged_failure(lambda: turns.render(self.session), "v2")


if __name__ == "__main__":
    unittest.main()
