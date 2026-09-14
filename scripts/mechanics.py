#!/usr/bin/env python3
"""只读机制计算器。JSON 是数据，不是指令；不读取或修改游戏存档。

成功输出 {ok:true, command, result}，失败输出 {ok:false, error} 并退出 2。
仅导入已审阅的原版计算模块，不暴露原版模板、SQLite、角色确认等入口。
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import sys

# A read-only CLI must not create import caches either.
sys.dont_write_bytecode = True
from engine_core import dynamic_convergence as dc
from engine_core.faction import assess_faction_gap, nemesis_difficulty
from engine_core.golden_finger import gf_scale
from engine_core.ripple import assess_ripple, compatibility_k
from engine_core.textkit import split_values
from engine_core.tropes import DEFAULT_TROPE_FILES, TropeStore

DATA_DIR = Path(__file__).resolve().parents[1] / "assets" / "data"
CHOICE_STYLES = ("强硬", "隐忍", "智取", "示弱", "反将", "借势", "试探", "斡旋", "收买")
MAX_INPUT_BYTES = 1024 * 1024


def object_fields(value, required, optional=(), label="输入"):
    if type(value) is not dict:
        raise ValueError(f"{label}必须是 JSON 对象")
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown:
        raise ValueError(f"{label}含未知字段：{', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{label}缺少字段：{', '.join(sorted(missing))}")
    return value


def number(value, label, lo=0, hi=None, integer=False):
    if (type(value) is not int if integer else type(value) not in (int, float)):
        raise ValueError(f"{label}必须是{'整数' if integer else '有限数值'}（不接受布尔值）")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < lo or (hi is not None and value > hi):
        raise ValueError(f"{label}超出范围 [{lo}, {hi if hi is not None else '有限上界'}]")
    return value


def text(value, label):
    if type(value) is not str or len(value) > 20000:
        raise ValueError(f"{label}必须是长度不超过 20000 的字符串")
    return value


def enum(value, choices, label):
    if type(value) is not str or value not in choices:
        raise ValueError(f"{label}必须是 {' / '.join(choices)} 之一")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 重复字段：{key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError(f"JSON 不允许非有限数值：{value}")


def read_input(filename):
    target = Path(filename)
    if not target.is_file():
        raise ValueError("输入必须是普通 JSON 文件")
    with target.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("输入文件不能超过 1 MiB")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                      parse_constant=_bad_constant)


def calculate_ripple(data):
    object_fields(data, ("breadth", "persistence", "canon_conflict", "progress",
                         "difficulty", "pressure", "current_total", "convergence"))
    for key in ("breadth", "persistence", "canon_conflict"):
        number(data[key], key, 0, 4, integer=True)
    number(data["progress"], "progress", 0, 1)
    number(data["difficulty"], "difficulty", 1, 9, integer=True)
    number(data["pressure"], "pressure", 0, 3, integer=True)
    number(data["current_total"], "current_total", 0, integer=True)
    enum(data["convergence"], dc.TIERS, "convergence")
    return asdict(assess_ripple(**data))


def calculate_k(data):
    object_fields(data, ("action",), ("anchor", "style", "trigger_overlap"))
    text(data["action"], "action")
    text(data.get("anchor", ""), "anchor")
    if data.get("style") is not None:
        text(data["style"], "style")
    number(data.get("trigger_overlap", 0), "trigger_overlap", 0, integer=True)
    value = compatibility_k(**data)
    return {"k": value, "compatible": value >= 60}


def validate_members(members, label):
    if type(members) is not list or len(members) > 3:
        raise ValueError(f"{label}必须是最多 3 位成员的数组（主角本人另填）")
    strings = ("name", "description", "skill", "background", "role")
    for member in members:
        object_fields(member, (), strings + ("power", "influence", "scope",
                      "scope_coefficient", "permanence", "residency"), label)
        for first, alias, upper, integer in (("power", "influence", 4, True),
                ("scope", "scope_coefficient", 1.5, False),
                ("permanence", "residency", 1, False)):
            if first in member and alias in member:
                raise ValueError(f"{label}不能同时指定 {first} 与 {alias}")
            for key in (first, alias):
                if key in member:
                    number(member[key], key, 0, upper, integer=integer)
        for key in strings:
            if key in member:
                text(member[key], key)


def calculate_faction(data):
    object_fields(data, ("members",), ("opposing_members", "protagonist_power",
                                       "genre", "player_difficulty"))
    validate_members(data["members"], "members")
    validate_members(data.get("opposing_members", []), "opposing_members")
    number(data.get("protagonist_power", 2), "protagonist_power", 0, 4, integer=True)
    number(data.get("player_difficulty", 4), "player_difficulty", 1, 9, integer=True)
    text(data.get("genre", ""), "genre")
    kwargs = {key: value for key, value in data.items() if key != "player_difficulty"}
    result = assess_faction_gap(**kwargs)
    result["nemesis_difficulty"] = nemesis_difficulty(**data)
    return result


def _tier(position):
    return "一般" if position < 0.25 else "较高" if position <= 0.75 else "极高"


def _position(value, base, label):
    return number(value, label, 0.25 if base == "极高" else 0,
                  0.75 if base == "一般" else 1)


def validate_conv(conv):
    object_fields(conv, ("base", "position", "effective", "last_settled_position", "history"), label="conv")
    base = enum(conv["base"], dc.TIERS, "conv.base")
    _position(conv["position"], base, "conv.position")
    _position(conv["last_settled_position"], base, "conv.last_settled_position")
    if enum(conv["effective"], dc.TIERS, "conv.effective") != _tier(conv["position"]):
        raise ValueError("conv.effective 与 position 不一致")
    history = conv["history"]
    if type(history) is not list or len(history) > dc.HISTORY_LIMIT:
        raise ValueError("conv.history 必须是最多 20 条的数组")
    for entry in history:
        object_fields(entry, ("outcome", "position", "effective"), ("round",), "history条目")
        enum(entry["outcome"], dc.OUTCOMES, "history.outcome")
        _position(entry["position"], base, "history.position")
        if enum(entry["effective"], dc.TIERS, "history.effective") != _tier(entry["position"]):
            raise ValueError("history.effective 与 position 不一致")
        if "round" in entry:
            number(entry["round"], "history.round", 0, integer=True)
    if history and history[-1]["position"] != conv["position"]:
        raise ValueError("history 最后位置与 conv.position 不一致")


def calculate_convergence(data):
    object_fields(data, (), ("base", "conv", "outcome", "weight", "round"))
    if "base" in data:
        object_fields(data, ("base",))
        conv = dc.init_state(enum(data["base"], dc.TIERS, "base"))
    else:
        object_fields(data, ("conv", "outcome"), ("weight", "round"))
        validate_conv(data["conv"])
        enum(data["outcome"], dc.OUTCOMES, "outcome")
        number(data.get("weight", 1.0), "weight", 0)
        if data.get("round") is not None:
            number(data["round"], "round", 0, integer=True)
        conv = dc.settle(copy.deepcopy(data["conv"]), data["outcome"],
                         weight=data.get("weight", 1.0), round=data.get("round"))
    return {"conv": conv, "thresholds": dc.thresholds_for(conv)}


def calculate_gf(difficulty):
    number(difficulty, "difficulty（宿敌 D）", 0.01, 9.99)
    return {"nemesis_d": difficulty, "gf_scale": gf_scale(difficulty)}


def load_fixed_store():
    # Never use paths supplied by JSON, a manifest, or the user. Never call load()
    # or from_sqlite(): those upstream APIs can open/create arbitrary databases.
    rows = []
    for name in DEFAULT_TROPE_FILES:
        rows.extend(TropeStore.from_json(DATA_DIR / name).tropes)
    return TropeStore(rows)


def search_tropes(query, cat=None, style=None, limit=5):
    text(query, "query")
    number(limit, "limit", 1, 50, integer=True)
    if cat is not None:
        text(cat, "cat")
    if style is not None:
        enum(style, CHOICE_STYLES, "style")
    store = load_fixed_store()
    categories = {trope.cat for trope in store.tropes}
    if cat is not None and cat not in categories:
        raise ValueError("cat 必须是桥段记录的完整分类名")
    terms = set(term.lower() for term in split_values(query))
    ranked = []
    # Upstream search() handles exact category/style filtering. Upstream trigger
    # search is exact-only; substring ranking here makes full natural-language
    # trigger sentences and names discoverable using short Chinese queries.
    candidates = store.search(cat=cat, style=style, limit=len(store.tropes))
    for index, trope in enumerate(candidates):
        blob = " ".join(str(value) for value in trope.data.values()).lower()
        hits = sum(term in blob for term in terms)
        if terms and not hits:
            continue
        ranked.append((hits, -index, trope))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    items = [{"id": trope.id, "cat": trope.cat, "style": trope.style,
              "triggers": trope.triggers, "data": dict(trope.data)}
             for _, _, trope in ranked[:limit]]
    return {"total_records": len(store.tropes), "matched": len(ranked),
            "returned": len(items), "items": items}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f"命令行参数错误：{message}")


def parser():
    result = Parser(description=__doc__, allow_abbrev=False)
    sub = result.add_subparsers(dest="command", required=True)
    for command in ("ripple", "k", "faction", "convergence"):
        sub.add_parser(command, allow_abbrev=False).add_argument("--input", required=True)
    sub.add_parser("gf", allow_abbrev=False).add_argument("--difficulty", required=True, type=float)
    tropes = sub.add_parser("tropes", allow_abbrev=False)
    tropes.add_argument("--query", required=True)
    tropes.add_argument("--cat")
    tropes.add_argument("--style", choices=CHOICE_STYLES)
    tropes.add_argument("--limit", type=int, default=5)
    return result


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"不可序列化的结果：{type(value).__name__}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        args = parser().parse_args(argv)
        if args.command == "gf":
            result = calculate_gf(args.difficulty)
        elif args.command == "tropes":
            result = search_tropes(args.query, args.cat, args.style, args.limit)
        else:
            data = read_input(args.input)
            if args.command == "ripple":
                result = calculate_ripple(data)
            elif args.command == "k":
                result = calculate_k(data)
            elif args.command == "faction":
                result = calculate_faction(data)
            elif args.command == "convergence":
                result = calculate_convergence(data)
            else:
                raise ValueError("未知计算器")
        print(json.dumps({"ok": True, "command": args.command, "result": result},
                         ensure_ascii=False, allow_nan=False, default=_json_default))
        return 0
    except (ValueError, TypeError, OSError, RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": f"计算失败：{exc}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
