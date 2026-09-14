"""Independent standard-library regression tests: python -B test_mechanics.py."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import mechanics as m
from engine_core import dynamic_convergence as dc
from engine_core.faction import assess_faction_gap, assess_member, nemesis_difficulty
from engine_core.golden_finger import gf_scale
from engine_core.ripple import assess_ripple, compatibility_k, impact_level, ripple_threshold
from engine_core.tropes import DEFAULT_TROPE_FILES, TropeStore

SCRIPT = Path(__file__).with_name("mechanics.py")
RIPPLE = dict(breadth=4, persistence=4, canon_conflict=4, progress=0.8,
              difficulty=4, pressure=3, current_total=3, convergence="较高")


class FormulaTests(unittest.TestCase):
    def test_all_thresholds(self):
        expected = {"一般": [4, 4, 4, 4, 5, 5, 5, 5, 6],
                    "较高": [6, 6, 6, 6, 7, 7, 7, 7, 8],
                    "极高": [8, 8, 8, 8, 10, 10, 10, 10, 11]}
        for tier, values in expected.items():
            for d, value in enumerate(values, 1):
                with self.subTest(tier=tier, d=d):
                    self.assertEqual(ripple_threshold(d, tier), value)

    def test_integer_impact_and_progress_gate(self):
        for b in range(5):
            for p in range(5):
                for c in range(5):
                    score = b * 0.75 + p * 0.75 + c
                    expected = min(4, int(score // 2))
                    result = m.calculate_ripple(dict(RIPPLE, breadth=b, persistence=p, canon_conflict=c))
                    self.assertEqual(result["raw_level"], expected)
                    self.assertEqual(result["score"], score)
        self.assertEqual(impact_level(1, 1, 1, 1), 1)
        self.assertEqual(impact_level(1.0, 1.0, 1.0, 1), 4)
        self.assertEqual(impact_level(4, 4, 4, 0.6), 3)
        self.assertEqual(impact_level(4, 4, 4, 0.600001), 4)
        self.assertFalse(m.calculate_ripple(dict(RIPPLE, progress=0.6))["allowed"])
        self.assertFalse(m.calculate_ripple(dict(RIPPLE, current_total=2))["allowed"])
        self.assertTrue(m.calculate_ripple(RIPPLE)["allowed"])

    def test_k_actual_signature_and_bounds(self):
        self.assertEqual(compatibility_k("", ""), 0)
        self.assertEqual(compatibility_k("守护朋友", "守护朋友"), 95)
        self.assertEqual(compatibility_k("守护朋友", "守护朋友", "朋友", 4), 100)
        self.assertEqual(m.calculate_k({"action": "ABC", "anchor": "abc"})["k"], 95)
        self.assertEqual(m.calculate_k({"action": "x", "anchor": "y", "trigger_overlap": 999})["k"], 20)
        self.assertFalse(m.calculate_k({"action": "x", "anchor": "y"})["compatible"])

    def test_member_and_factions(self):
        member = assess_member({"name": "盟友", "power": 4, "scope": 1.5, "permanence": 0.5})
        self.assertEqual(member.effective, 3)
        self.assertEqual(assess_member({"influence": 3}, "都市").dimension, "影响力")
        self.assertEqual(assess_member({"skill": "远强"}).power, 4)
        strong = assess_faction_gap([{"power": 4}])
        peers = assess_faction_gap([{"power": 2}] * 3)
        self.assertGreater(strong["aggregate"], peers["aggregate"])
        self.assertEqual(strong["aggregate"], 5)
        self.assertEqual(peers["aggregate"], 3.308)
        for d in range(1, 10):
            self.assertEqual(nemesis_difficulty(d), 10 - d)
        value = m.calculate_faction({"members": [], "opposing_members": [{"power": 4}]})
        self.assertEqual(value["delta"], 3)
        self.assertEqual(value["nemesis_bonus"], 3)
        self.assertEqual(value["nemesis_difficulty"], round(6 - 3 * (1 - math.exp(-2.4)), 2))
        self.assertEqual(nemesis_difficulty(9, (), 0, "", [{"power": 4}] * 3), 0.01)
        self.assertEqual(nemesis_difficulty(1, [{"power": 4}] * 3, 4, "", [{"power": 0}]), 9.99)
        self.assertEqual(m.calculate_faction({"members": [{"influence": 4, "scope_coefficient": 1.5, "residency": 0.5}], "genre": "职场"})["aggregate"], 4)

    def test_gf_formula_and_clamps(self):
        for d in (0.01, 0.1, 1.0, 4.0, 6.35, 9.99):
            self.assertEqual(gf_scale(d), round(max(0.01, min(13, d ** 1.15)), 4))
            self.assertEqual(m.calculate_gf(d)["gf_scale"], gf_scale(d))
        self.assertEqual(gf_scale(0.01), 0.01)
        self.assertEqual(gf_scale(1), 1)
        self.assertEqual(gf_scale(9.99), 13)

    def test_dynamic_steps_and_regression(self):
        self.assertEqual(dc.init_state("一般")["position"], 0.125)
        for outcome, expected in (("faithful", 0.45), ("offset", 0.55), ("reversed", 0.575), ("none", 0.5)):
            conv = dc.settle(dc.init_state("较高"), outcome, weight=100)
            self.assertAlmostEqual(conv["position"], expected)
        conv = dc.init_state("较高")
        dc.settle(conv, "reversed", weight=100)
        self.assertAlmostEqual(conv["position"] - conv["last_settled_position"], 0.075)
        dc.settle(conv, "none", weight=100)
        self.assertAlmostEqual(conv["position"], 0.55)
        self.assertAlmostEqual(dc.settle(dc.init_state("较高"), "offset", weight=0)["position"], 0.505)

    def test_dynamic_bounds_history_and_no_mutation(self):
        for base, outcome, end in (("极高", "faithful", 0.25), ("一般", "reversed", 0.75),
                                   ("较高", "faithful", 0), ("较高", "reversed", 1)):
            conv = dc.init_state(base)
            for i in range(100):
                dc.settle(conv, outcome, weight=100, round=i)
            self.assertEqual(conv["position"], end)
            self.assertEqual(len(conv["history"]), 20)
            self.assertEqual(conv["history"][0]["round"], 80)
            m.validate_conv(conv)
        data = {"conv": dc.init_state("较高"), "outcome": "offset", "round": 0}
        before = copy.deepcopy(data)
        result = m.calculate_convergence(data)
        self.assertEqual(data, before)
        self.assertEqual(result["conv"]["history"][-1]["round"], 0)
        self.assertEqual(m.calculate_convergence({"base": "较高"})["thresholds"], {"down": 0.25, "up": 0.75})


class ValidationTests(unittest.TestCase):
    def test_ripple_invalid_types_and_ranges(self):
        invalid = {"breadth": [-1, 5, 1.0, True, "1", None],
                   "persistence": [0.5, False], "canon_conflict": [4.0, 5],
                   "progress": [-0.1, 1.1, float("nan"), float("inf"), True],
                   "difficulty": [0, 10, 4.0, False], "pressure": [-1, 4, 1.0],
                   "current_total": [-1, 1.0, True], "convergence": ["低", "较高(默认)", None]}
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    m.calculate_ripple(dict(RIPPLE, **{key: value}))
        for key in RIPPLE:
            data = dict(RIPPLE)
            del data[key]
            with self.assertRaises(ValueError):
                m.calculate_ripple(data)

    def test_reject_unknown_fields_and_privileges(self):
        cases = [(m.calculate_ripple, RIPPLE), (m.calculate_k, {"action": "abc"}),
                 (m.calculate_faction, {"members": []}),
                 (m.calculate_convergence, {"base": "较高"})]
        for calculator, data in cases:
            for key in ("cheat", "god_mode", "provider", "module", "path", "confirmed"):
                with self.subTest(calc=calculator.__name__, key=key), self.assertRaises(ValueError):
                    calculator(dict(data, **{key: True}))
        with self.assertRaises(ValueError):
            m.calculate_faction({"members": [{"name": "x", "golden_finger": "无敌"}]})
        for member in ({"power": True}, {"power": 2, "influence": 3},
                       {"scope": 2}, {"permanence": -1}, {"scope": 1, "scope_coefficient": 1}):
            with self.assertRaises(ValueError):
                m.calculate_faction({"members": [member]})
        with self.assertRaises(ValueError):
            m.calculate_faction({"members": [{}] * 4})
        with self.assertRaises(ValueError):
            m.calculate_k({"action": {"__class__": "unsafe"}})

    def test_convergence_validation(self):
        valid = {"conv": dc.init_state("较高"), "outcome": "faithful"}
        for key, values in (("outcome", ["cheat", None]), ("weight", [-1, True, float("nan")]),
                            ("round", [-1, 1.5, True])):
            for value in values:
                with self.assertRaises(ValueError):
                    m.calculate_convergence(dict(valid, **{key: value}))
        for key, value in (("position", 2), ("effective", "一般"), ("history", [{}]),
                           ("base", "未知"), ("god_mode", True)):
            conv = dict(valid["conv"], **{key: value})
            with self.assertRaises(ValueError):
                m.calculate_convergence(dict(valid, conv=conv))
        for base, pos in (("一般", 0.8), ("极高", 0.2)):
            conv = dict(dc.init_state(base), position=pos, effective=m._tier(pos))
            with self.assertRaises(ValueError):
                m.validate_conv(conv)
        conv = dc.init_state("较高")
        conv["history"] = [{"outcome": "faithful", "position": 0.5, "effective": "较高", "cheat": True}]
        with self.assertRaises(ValueError):
            m.validate_conv(conv)
        with self.assertRaises(ValueError):
            m.calculate_convergence(dict(valid, base="较高"))

    def test_gf_validation(self):
        for d in (0, -1, 10, float("nan"), float("inf"), True, "4"):
            with self.assertRaises(ValueError):
                m.calculate_gf(d)

    def test_json_duplicate_nan_and_size(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "input.json"
            for content in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}',
                            '{"nested":{"x":1,"x":2}}', '{} trailing', 'x' * (m.MAX_INPUT_BYTES + 1)):
                target.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    m.read_input(target)
            target.write_bytes(b'\xef\xbb\xbf{"action":"hello"}')
            self.assertEqual(m.read_input(target), {"action": "hello"})


class AssetTests(unittest.TestCase):
    def test_count_schema_and_manifest(self):
        counts = (680, 685, 680, 680, 684)
        records = []
        for name, count in zip(DEFAULT_TROPE_FILES, counts):
            raw = json.loads((m.DATA_DIR / name).read_text(encoding="utf-8"))
            self.assertEqual(len(raw), count)
            records.extend(raw)
        manifest = json.loads((m.DATA_DIR / "tropes_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["record_count"], 3409)
        self.assertEqual(tuple(manifest["files"]), DEFAULT_TROPE_FILES)
        self.assertEqual(set(manifest["choice_styles"]), set(m.CHOICE_STYLES))
        self.assertEqual(len({row["id"] for row in records}), 3409)
        self.assertTrue(all(set(row) == set(manifest["fields"]) for row in records))

    def test_full_assets_and_modules_match_upstream_when_available(self):
        source = SCRIPT.parents[4] / "_source" / "novelborne-3.0.1"
        if not source.is_dir():
            self.skipTest("Optional upstream source checkout is not installed")
        for name in ("textkit", "ripple", "faction", "golden_finger", "dynamic_convergence", "tropes"):
            self.assertEqual((source / "core/engine" / (name + ".py")).read_bytes(),
                             (SCRIPT.parent / "engine_core" / (name + ".py")).read_bytes())
        for name in (*DEFAULT_TROPE_FILES, "tropes_manifest.json"):
            self.assertEqual((source / "assets/data" / name).read_bytes(), (m.DATA_DIR / name).read_bytes())

    def test_all_libraries_searchable_and_original_exact_search(self):
        for prefix in ("TB", "TC", "TL", "TM", "TR"):
            found = m.search_tropes(prefix + "-0001")
            self.assertEqual(found["returned"], 1)
            self.assertEqual(found["items"][0]["id"], prefix + "-0001")
            self.assertIn("reaction", found["items"][0]["data"])
        found = m.search_tropes("借刀", cat="商战·权谋·布局", style="借势", limit=3)
        self.assertGreater(found["matched"], 0)
        self.assertLessEqual(found["returned"], 3)
        self.assertTrue(all("借势" in row["data"]["choice_styles"] for row in found["items"]))
        store = m.load_fixed_store()
        trope = store.tropes[0]
        self.assertIn(trope, store.search(triggers=trope.triggers))
        self.assertEqual(m.search_tropes("not-a-real-trope-213124")["items"], [])
        self.assertEqual(m.search_tropes("", limit=50)["returned"], 50)
        self.assertEqual(m.search_tropes("TB-0001、TC-0001")["returned"], 2)
        for kwargs in ({"limit": 0}, {"limit": 51}, {"style": "行动型"}, {"cat": "../../data"}):
            with self.assertRaises(ValueError):
                m.search_tropes("", **kwargs)

    def test_never_dispatch_sqlite_or_template(self):
        with patch.object(TropeStore, "from_sqlite", side_effect=AssertionError("SQLite forbidden")), \
             patch.object(TropeStore, "load", side_effect=AssertionError("Dynamic load forbidden")):
            result = m.search_tropes("TB-0001")
        self.assertIn("{主角}", result["items"][0]["data"]["reaction"])


class CLITests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=cwd,
                                capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout), result.stdout

    def test_cli_whitelist_utf8_and_all_commands_no_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            target = folder / "input.json"
            cases = [("ripple", RIPPLE), ("k", {"action": "守护", "anchor": "守护"}),
                     ("faction", {"members": [{"name": "盟友", "power": 4}]}),
                     ("convergence", {"base": "较高"}),
                     ("convergence", {"conv": dc.init_state("较高"), "outcome": "reversed", "weight": 100})]
            for command, data in cases:
                target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                before = target.read_bytes()
                code, output, raw = self.run_cli(command, "--input", str(target), cwd=folder)
                self.assertEqual(code, 0, output)
                self.assertTrue(output["ok"])
                self.assertEqual(output["command"], command)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(list(folder.iterdir()), [target])
                self.assertNotIn("\\u", raw)
            code, output, _ = self.run_cli("gf", "--difficulty", "9.99", cwd=folder)
            self.assertEqual(code, 0)
            self.assertEqual(output["result"]["gf_scale"], 13)
            code, output, _ = self.run_cli("tropes", "--query", "借刀", "--limit", "2", cwd=folder)
            self.assertEqual(code, 0)
            self.assertGreater(output["result"]["returned"], 0)
            for args in (("eval",), ("gf", "--difficulty", "nan"),
                         ("gf", "--difficulty", "4", "--provider", "x"),
                         ("tropes", "--query", "", "--path", str(target)),
                         ("gf", "--diff", "4")):
                code, output, _ = self.run_cli(*args, cwd=folder)
                self.assertEqual(code, 2)
                self.assertFalse(output["ok"])


if __name__ == "__main__":
    unittest.main()
