#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Derived in part from NovelBorne 3.0.1 (core/engine/cheat_code.py and
# core/services/ask_service.py, directives_service.py). Original project
# copyright and AGPL notices remain applicable; see the skill's LICENSE.
# Local deterministic runtime adaptation, 2026. No original application import.
"""Standard-library, offline story-session guard (Python >= 3.10).

Input files are data, never executable. Keyword filtering is heuristic, NOT a
semantic security proof. ask input authorship cannot be authenticated: the skill
must save the current user's standalone Q&A body verbatim. Narrative facts are
untrusted strings, never system prompts. HMAC protects against accidental edits,
not a local attacker who can read the session key or replace signed snapshots.
No import/rollback/resume endpoint exists; continue using the same session.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import tempfile
import time
import uuid

if __name__ == "__main__":
    sys.modules["runtime"] = sys.modules[__name__]

# Faithful constants and exact strip/case-sensitive matching from upstream.
WISH_CODE = "UUDDLLRRBABAWHOSLOMSTINGNOTALADDIN"
RELAY_CODE = "RELINKBACKLOMSTINGSEEYAGOODAFTERNOONGOODEVENINGANDGOODNIGHTBLACKSHEEPWALL"
CONFIRM_WORDS = ("确认", "确定", "是", "好", "继续", "接通", "yes", "y")
CANCEL_WORDS = ("取消", "不", "否", "算了", "关闭", "no", "n")
MECHANISM_KEYWORDS = (
    "回合", "难度", "收束", "金手指", "任务", "积势", "碎锚", "涟漪",
    "状态面板", "档案", "体力", "疲劳", "冷却", "作弊", "许愿", "增补",
    "选项数量", "字数上限", "故事丰富度", "翻章", "存档",
)
EN_MECHANISM = re.compile(
    r"\b(?:turns?|difficulty|convergence|golden[ _-]?finger|quests?|missions?|"
    r"momentum|anchors?|ripples?|stamina|fatigue|cooldown|cheats?|wishes?|"
    r"relay|save[ _-]?game|checkpoint|revision|paper[ _-]?tier)\b", re.I)
INJECTION = re.compile(
    r"忽略.{0,12}(?:规则|指令|要求)|无视.{0,12}(?:规则|指令)|系统提示|系统指令|"
    r"开发者|执行.{0,8}(?:文件|代码|脚本|命令)|命令行|认证角色|伪造.{0,8}(?:身份|角色)|"
    r"越权|绕过.{0,8}(?:规则|限制|验证)|管理员权限|覆盖.{0,8}(?:规则|指令)|"
    r"\b(?:ignore|disregard|override|bypass)\b.{0,60}\b(?:rules?|instructions?|polic\w*|previous|system)\b|"
    r"\b(?:system\s*(?:prompt|message|role)|developer|fake\s+system|"
    r"json\s*patch|base64|sudo|powershell|cmd\.exe|eval|exec)\b|"
    r"\b(?:run|execute)\b.{0,40}\b(?:file|code|command|script|shell)\b|"
    r"\b(?:authenticate|impersonate)\b.{0,40}\b(?:role|admin|system)\b|"
    r"<\s*/?\s*(?:system|developer|tool)\b|\[\s*(?:system|developer)\s*\]|"
    r"[\"']role[\"']\s*:\s*[\"'](?:system|developer)|"
    r"(?:__import__|subprocess|os\.system)\s*\(", re.I)
PROTECTED = {
    "config", "cheats", "cheat_wish", "wish", "wish_limit", "used_count", "armed",
    "wish_facts", "relay", "relay_activated", "relay_facts", "relay_confirm_pending",
    "turn", "phase", "revision", "expected_revision", "session_id", "signature",
    "hmac", "key", "options", "pending", "pending_action", "events", "world",
    "anchors_disabled", "anchor_distillation_disabled", "distill_status",
    "anchors_shattered_from", "config_locked", "locked_config_sha256",
    "difficulty", "mode", "convergence", "paper_tier", "story_agent_mode",
    "source_index", "version", "setup", "semantic_coverage", "preparation", "pipeline",
    "pipeline_token", "mechanical", "ripple_total", "chapter_turn", "setup_confirmed",
    "gf_confirmed", "cast_confirmed", "issued", "chunks", "proposed_mechanical", "last_turn_audit",
}
PROTECTED_NORMALIZED = {re.sub(r"[^a-z0-9]", "", key.lower()) for key in PROTECTED}
MAX_SOURCE = 32 * 1024 * 1024
MAX_STATE = 16 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_TEXT = 64 * 1024
CHAPTER = re.compile(
    r"^[ \t]*(?:(?:第[〇零一二三四五六七八九十百千万两\d]+[章节回卷部篇].*)|"
    r"(?:(?:chapter|chap\.?|book|part)\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[^\r\n]*)|"
    r"(?:序章|序幕|楔子|前言|引子|终章|尾声|后记|prologue|epilogue)(?:[ \t:：].*)?)[ \t]*\r?$",
    re.I | re.M)


class RuntimeError_(ValueError):
    """Public errors have fixed safe descriptions, never rejected input text."""


def require(condition, message):
    if not condition:
        raise RuntimeError_(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path, limit):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), "input_must_be_regular_file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "file_size_limit")
    return data


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def parse_json(data):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(RuntimeError_("nonfinite_json")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RuntimeError_("invalid_utf8_json") from exc


def load_json(path, limit=MAX_JSON):
    return parse_json(read_bytes(path, limit))


def text_file(path):
    try:
        # No normalization or BOM stripping: the caller supplies the actual body.
        text = read_bytes(path, MAX_TEXT).decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError_("text_file_must_be_utf8") from exc
    require(bool(text.strip()), "empty_text")
    return text


def shape(obj, required, optional=()):
    require(type(obj) is dict, "object_required")
    require(set(required) <= obj.keys() and obj.keys() <= set(required) | set(optional),
            "invalid_object_fields")


def string(value, maximum=4000, empty=False):
    require(type(value) is str and len(value) <= maximum and (empty or bool(value.strip())),
            "invalid_string")
    require(not any(ord(c) < 32 and c not in "\r\n\t" for c in value), "control_character")
    return value


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, "invalid_integer")
    return value


def protected_data(value, depth=0):
    """Reject protected field names recursively, including JSON encoded in strings.

    Does not treat JSON narrative snapshots as executable patches. Only their
    keys are checked, and the original string is retained as non-authority data.
    """
    require(depth < 25, "nesting_limit")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            require(normalized not in PROTECTED_NORMALIZED and not key.startswith("__"),
                    "protected_field")
            protected_data(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            protected_data(child, depth + 1)
    elif isinstance(value, str):
        require(not INJECTION.search(value), "instruction_injection")
        if value.lstrip().startswith(("{", "[")):
            try:
                nested = parse_json(value.encode("utf-8"))
            except RuntimeError_:
                nested = None
            if isinstance(nested, (dict, list)):
                protected_data(nested, depth + 1)
        for key in re.findall(r'["\']([^"\']+)["\']\s*:', value):
            require(re.sub(r"[^a-z0-9]", "", key.lower()) not in PROTECTED_NORMALIZED,
                    "protected_field")


def turn_budget(chars):
    integer(chars, 0, MAX_SOURCE)
    return next((3 + i for i, bound in enumerate((1500, 3000, 5000, 8000, 12000, 18000))
                 if chars < bound), 9)


def decode_source(raw):
    # Strict, deterministic precedence. UTF-32 is deliberately unsupported.
    require(not raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")), "unsupported_utf32")
    if raw.startswith(b"\xef\xbb\xbf"):
        encodings = ["utf-8-sig"]
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"]
    else:
        encodings = ["utf-8", "gb18030"]
    for encoding in encodings:
        try:
            text = raw.decode(encoding, errors="strict")
            require("\x00" not in text, "nul_in_source")
            require(bool(text.strip()), "empty_source")
            return text, encoding
        except UnicodeError:
            continue
    raise RuntimeError_("source_decode_failed")


def build_index(text, raw, encoding):
    matches = list(CHAPTER.finditer(text))
    boundaries = [(match.start(), match.group().strip()) for match in matches]
    if not boundaries or boundaries[0][0] != 0:
        boundaries.insert(0, (0, "未分章" if not matches else "卷首片段"))
    chapters = []
    for i, (start, title) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        chapters.append({"id": f"ch{i + 1:04d}", "title": title, "start": start,
                         "end": end, "chars": end - start, "turn_budget": turn_budget(end - start)})
    return {"version": 1, "encoding": encoding, "raw_sha256": sha(raw),
            "text_sha256": sha(text.encode("utf-8")), "chars": len(text),
            "offset_unit": "unicode_code_points", "interval": "start_inclusive_end_exclusive",
            "coverage": "indexed_only_not_semantically_covered", "chapters": chapters}


def safe_directory(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), "symlink_path_not_allowed")
    return path


def write_new(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(source, out):
    raw = read_bytes(source, MAX_SOURCE)
    text, encoding = decode_source(raw)
    index = build_index(text, raw, encoding)
    destination = safe_directory(out)
    require(not destination.exists(), "output_directory_already_exists")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        write_new(destination / "source.txt", text.encode("utf-8"))
        write_new(destination / "index.json", canonical(index))
    except Exception:
        shutil.rmtree(destination)
        raise
    return {"prepared": str(destination), "index": index}


def prepared_data(directory):
    directory = safe_directory(directory)
    index = load_json(directory / "index.json", MAX_STATE)
    raw = read_bytes(directory / "source.txt", MAX_SOURCE * 3)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError_("prepared_source_not_utf8") from exc
    shape(index, ("version", "encoding", "raw_sha256", "text_sha256", "chars", "offset_unit",
                  "interval", "coverage", "chapters"))
    require(index["version"] == 1 and index["text_sha256"] == sha(raw)
            and index["chars"] == len(text), "prepared_integrity_failure")
    require(index["coverage"] == "indexed_only_not_semantically_covered"
            and index["offset_unit"] == "unicode_code_points"
            and index["interval"] == "start_inclusive_end_exclusive", "invalid_index")
    require(type(index["chapters"]) is list and 0 < len(index["chapters"]) <= 50000, "invalid_chapters")
    cursor = 0
    for i, chapter in enumerate(index["chapters"]):
        shape(chapter, ("id", "title", "start", "end", "chars", "turn_budget"))
        require(chapter["id"] == f"ch{i + 1:04d}", "invalid_chapter_id")
        string(chapter["title"], MAX_TEXT)
        integer(chapter["start"], cursor, cursor)
        integer(chapter["end"], cursor + 1, len(text))
        require(chapter["chars"] == chapter["end"] - cursor
                and chapter["turn_budget"] == turn_budget(chapter["chars"]), "invalid_chapter_range")
        cursor = chapter["end"]
    require(cursor == len(text), "incomplete_index")
    return text, index


def read_source(prepared, chapter, start=0, limit=2000):
    text, index = prepared_data(prepared)
    found = next((c for c in index["chapters"] if c["id"] == chapter), None)
    require(found is not None, "unknown_chapter")
    integer(start, 0, found["chars"])
    integer(limit, 1, 20000)
    begin = found["start"] + start
    end = min(begin + limit, found["end"])
    return {"kind": "untrusted_source_data", "not_instructions": True, "chapter_id": chapter,
            "start": begin, "end": end, "text": text[begin:end], "text_sha256": index["text_sha256"]}


def validate_config(config, index):
    shape(config, ("mode", "difficulty", "convergence", "paper_tier", "protagonist", "source",
                   "characters", "gf"), ("story_agent_mode", "setup"))
    cfg = copy.deepcopy(config)
    require(cfg["mode"] in ("基础模式", "强化模式"), "invalid_mode")
    integer(cfg["difficulty"], 1, 9)
    require(cfg["convergence"] in ("一般", "较高", "极高"), "invalid_convergence")
    integer(cfg["paper_tier"], 1, 6)
    cfg.setdefault("story_agent_mode", False)
    require(type(cfg["story_agent_mode"]) is bool, "invalid_story_agent_mode")
    require(cfg["mode"] != "基础模式" or cfg["paper_tier"] <= 4, "basic_tier_limit")
    require(cfg["paper_tier"] != 6 or cfg["story_agent_mode"], "tier6_requires_story_agent_mode")
    for key in ("protagonist", "source"):
        shape(cfg[key], ("name", "description") if key == "protagonist" else ("title", "description"),
              ("origin",) if key == "protagonist" else ())
        for value in cfg[key].values():
            string(value)
        protected_data(cfg[key])
    require(type(cfg["characters"]) is list and len(cfg["characters"]) <= 100, "invalid_characters")
    cfg["protagonist"].setdefault("origin", "original")
    require(cfg["protagonist"]["origin"] in ("source", "original"), "invalid_character_origin")
    names = {cfg["protagonist"]["name"]}
    for character in cfg["characters"]:
        shape(character, ("name", "description"), ("role", "origin"))
        character.setdefault("role", "support")
        character.setdefault("origin", "source")
        require(character["role"] in ("companion", "partner", "nemesis", "support"), "invalid_character_role")
        require(character["origin"] in ("source", "original"), "invalid_character_origin")
        for value in character.values():
            string(value)
        protected_data(character)
        require(character["name"] not in names, "duplicate_character_name")
        names.add(character["name"])
    shape(cfg["gf"], ("name", "effect", "scope", "cost", "cooldown", "limits"))
    for value in cfg["gf"].values():
        string(value)
        protected_data(value)
    defaults = {"target_chapter": index["chapters"][0]["id"], "relative_time": "during",
                "fragment": "", "protagonist_gender": "unknown", "companions": 0, "partners": 0,
                "nemesis": False, "style": "", "preparation_mode": "fullbook" if cfg["mode"] == "强化模式" else "window",
                "semantic_coverage": []}
    setup = cfg.get("setup", {})
    shape(setup, (), defaults)
    setup = {**defaults, **setup}
    ids = {c["id"] for c in index["chapters"]}
    require(type(setup["target_chapter"]) is str and setup["target_chapter"] in ids, "unknown_target_chapter")
    require(setup["relative_time"] in ("before", "during", "after"), "invalid_relative_time")
    require(setup["protagonist_gender"] in ("male", "female", "unknown"), "invalid_gender")
    integer(setup["companions"], 0, 20)
    integer(setup["partners"], 0, 10)
    require(type(setup["nemesis"]) is bool, "invalid_nemesis")
    require(cfg["mode"] != "基础模式" or
            (setup["companions"] == setup["partners"] == 0 and not setup["nemesis"]), "basic_cast_limit")
    for key in ("fragment", "style"):
        string(setup[key], empty=True)
        protected_data(setup[key])
    require(setup["preparation_mode"] in ("window", "fullbook"), "invalid_preparation_mode")
    coverage = setup["semantic_coverage"]
    require(type(coverage) is list and all(type(c) is str and c in ids for c in coverage), "invalid_coverage")
    require(len(set(coverage)) == len(coverage), "duplicate_coverage")
    require(not coverage, "self_reported_coverage_forbidden_use_distill")
    require(cfg["mode"] != "强化模式" or setup["preparation_mode"] == "fullbook", "enhanced_requires_fullbook")
    for role, count in (("companion", setup["companions"]), ("partner", setup["partners"]),
                        ("nemesis", int(setup["nemesis"]))):
        require(sum(c["role"] == role for c in cfg["characters"]) == count, "configured_cast_count_mismatch")
    cfg["setup"] = setup
    return cfg


def signed(state, key):
    return canonical({"payload": state, "signature": hmac.new(key, canonical(state), hashlib.sha256).hexdigest()})


def atomic_state(directory, state, key):
    data = signed(state, key)
    require(len(data) <= MAX_STATE, "session_size_limit")
    fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, Path(directory) / "state.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create(root, config, prepared):
    text, index = prepared_data(prepared)
    cfg = validate_config(load_json(config), index)
    root = safe_directory(root)
    root.mkdir(parents=True, exist_ok=True)
    identifier = str(uuid.uuid4())
    session = root / identifier
    session.mkdir(exist_ok=False)
    state = {"version": 2, "session_id": identifier, "phase": "awaiting_opening", "revision": 0,
             "turn": 0, "config": cfg, "config_locked": False, "locked_config_sha256": None,
             "source_index": index, "options": [], "pending_action": None,
             "cheats": {"wish": {"armed": False, "used_count": 0, "limit": 3},
                        "relay": False, "relay_confirm_pending": False},
             "anchors_disabled": False, "anchor_distillation_disabled": False,
             "world": {"wish_facts": [], "relay_facts": [], "narrative_ledger": []}, "events": []}
    try:
        import preparation
        import turns
        preparation.initialize(state)
        turns.initialize(state)
        key = secrets.token_bytes(32)
        write_new(session / ".key", key)
        try:
            os.chmod(session / ".key", 0o600)
        except OSError:
            pass  # Windows ACL enforcement is not claimed.
        write_new(session / "source.txt", text.encode("utf-8"))
        write_new(session / "index.json", canonical(index))
        atomic_state(session, state, key)
    except Exception:
        shutil.rmtree(session)
        raise
    return {"session": str(session), "session_id": identifier, "phase": state["phase"], "revision": 0}


@contextlib.contextmanager
def locked(directory):
    directory = safe_directory(directory)
    require(directory.is_dir(), "session_not_found")
    lock = directory / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError_("session_busy_or_stale_lock") from exc
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
        yield directory
    finally:
        lock.unlink()


def load_session(directory):
    key = read_bytes(directory / ".key", 32)
    require(len(key) == 32, "invalid_session_key")
    envelope = load_json(directory / "state.json", MAX_STATE)
    shape(envelope, ("payload", "signature"))
    state = envelope["payload"]
    require(type(state) is dict and type(envelope["signature"]) is str, "invalid_signed_state")
    signature = hmac.new(key, canonical(state), hashlib.sha256).hexdigest()
    require(hmac.compare_digest(envelope["signature"], signature), "state_signature_mismatch")
    require(state.get("version") in (1, 2) and state.get("session_id") == directory.name, "session_identity_mismatch")
    if state.get("config_locked"):
        require(state["locked_config_sha256"] == sha(canonical(state["config"])), "locked_config_mismatch")
    return state, key


def transaction(session, operation):
    with locked(session) as directory:
        state, key = load_session(directory)
        require(state["version"] == 2, "legacy_session_readonly_export_or_use_v1")
        before = canonical(state)
        result = operation(state)
        if canonical(state) != before:
            state["revision"] += 1
            atomic_state(directory, state, key)
        return {**result, "revision": state["revision"], "turn": state["turn"]}


def confirm(session, text):
    def operation(state):
        require(text == "确认开局", "exact_opening_confirmation_required")
        require(state["phase"] == "awaiting_opening", "already_confirmed")
        import preparation
        preparation.ready(state)
        _, index = prepared_data(session)
        require(index == state["source_index"], "signed_source_index_mismatch")
        state["config_locked"] = True
        state["locked_config_sha256"] = sha(canonical(state["config"]))
        state["phase"] = "playing"
        state["events"].append({"type": "opening_confirmed"})
        return {"phase": "playing", "config_locked": True}
    return transaction(session, operation)


def sanitize_fact(text):
    string(text, 500)
    # Upstream Chinese period / semicolon sentence split, extended to English.
    sentences = [s.strip() for s in re.split(r"[。；;!?！？\r\n]+|\.(?=\s|$)", text) if s.strip()]
    kept, categories = [], []
    for sentence in sentences:
        if INJECTION.search(sentence):
            categories.append("instruction_injection")
        elif any(word in sentence for word in MECHANISM_KEYWORDS) or EN_MECHANISM.search(sentence):
            categories.append("mechanism_request")
        else:
            try:
                protected_data(sentence)
            except RuntimeError_:
                categories.append("protected_field")
            else:
                kept.append(sentence)
    return "。".join(kept), {"rejected_count": len(categories), "rejected_types": sorted(set(categories))}


def ask(session, path):
    return ask_text(session, text_file(path))


def ask_text(session, text, based_revision=None):
    question = text.strip()
    def operation(state):
        if based_revision is not None:
            require(state["revision"] == based_revision, "stale_revision")
        require(state["phase"] == "playing", "opening_not_confirmed")
        cheats, world = state["cheats"], state["world"]
        wish = cheats["wish"]
        # Precedence and confirmation vocabulary mirror upstream ask_service.
        if question == RELAY_CODE:
            if cheats["relay"]:
                return {"result": "relay_already_active_irreversible"}
            cheats["relay_confirm_pending"] = True
            return {"result": "relay_confirmation_required", "irreversible": True,
                    "effect": "session_only; disable_anchors_and_distillation; enable_multiselect_and_facts"}
        if cheats["relay_confirm_pending"]:
            if question.lower() in CONFIRM_WORDS:
                cheats["relay_confirm_pending"] = False
                cheats["relay"] = True
                state["anchors_disabled"] = True
                state["anchor_distillation_disabled"] = True
                state["events"].append({"type": "relay_activated"})
                return {"result": "relay_activated", "irreversible": True}
            if question.lower() in CANCEL_WORDS:
                cheats["relay_confirm_pending"] = False
                return {"result": "relay_confirmation_cancelled"}
            return {"result": "relay_confirmation_required"}
        if question == WISH_CODE:
            if wish["used_count"] >= 3:
                return {"result": "wish_exhausted", "wish_remaining": 0}
            wish["armed"] = True
            return {"result": "wish_armed", "wish_remaining": 3 - wish["used_count"]}
        if wish["armed"] and wish["used_count"] < 3 or cheats["relay"]:
            clean, notice = sanitize_fact(question)
            if not clean:
                return {"result": "fact_rejected", **notice}
            is_wish = wish["armed"] and wish["used_count"] < 3
            bucket = "wish_facts" if is_wish else "relay_facts"
            world[bucket].append(clean)
            state["events"].append({"type": "wish_fact" if is_wish else "relay_fact", "fact": clean,
                                    "data_only": True, **notice})
            if is_wish:  # Register first; consume only in the same atomic transaction.
                wish["used_count"] += 1
                wish["armed"] = False
            return {"result": "wish_registered" if is_wish else "relay_fact_registered", "data_only": True,
                    "wish_remaining": 3 - wish["used_count"], **notice}
        # No story generation, persistence or echo of arbitrary questions here.
        return {"result": "ordinary_question_no_state_change", "data_only": True}
    return transaction(session, operation)


def action(session, path):
    return action_text(session, text_file(path))


def action_text(session, body, based_revision=None):
    text = body.strip()
    explicit = text.startswith(("行动：", "行动:"))
    if explicit:
        text = text[3:].strip()
    elif text.startswith(("选择：", "选择:")):
        text = text[3:].strip()
    elif text.startswith("选择"):
        text = text[2:].strip()
    require(explicit or re.fullmatch(r"[A-F](?:[\s,，、+;/和与及]*[A-F])*(?:\s*[:：].+)?", text, re.S),
            "ambiguous_input_use_input_router")
    string(text, 4000)
    # Codes have no power outside ask, even embedded within an ordinary action.
    require(not INJECTION.search(text), "action_instruction_injection")
    protected_data(text)
    require(not re.search(r"(?:修改|设置|重置|取消|跳过|增加|减少|清空).{0,12}(?:回合|难度|冷却|机制|存档)|"
                          r"\b(?:set|reset|change|disable|increase|decrease)\b.{0,25}"
                          r"\b(?:difficulty|turn|cooldown|cheat|revision|mechanic)\b", text, re.I),
            "action_mechanism_request")
    def operation(state):
        if based_revision is not None:
            require(state["revision"] == based_revision, "stale_revision")
        require(state["phase"] == "playing" and len(state["options"]) == 6, "action_requires_opening_options")
        require(state["pending_action"] is None, "action_already_pending")
        import turns
        turns.require_action_budget(state)
        # IDs must be explicit tokens. E.g. A,C plus optional free intent.
        option_match = re.fullmatch(r"([A-F](?:[\s,，、+;/和与及]*[A-F])*)(?:\s*[:：]\s*(.+))?", text, re.S)
        selected = re.findall(r"[A-F]", option_match.group(1)) if option_match else []
        # Reject ID-prefix multiselect disguised as free prose in normal mode too.
        prefix = re.match(r"^([A-F](?:[\s,，、+;/和与及]+[A-F])+)", text)
        if prefix and not selected:
            selected = re.findall(r"[A-F]", prefix.group(1))
        if not selected:
            # Also catch explicit option IDs in prose such as 选择A和B. Letters
            # embedded in Latin words or the opaque codes are not option IDs.
            selected = re.findall(r"(?<![A-Za-z0-9_])[A-F](?![A-Za-z0-9_])", text)
        require(len(selected) == len(set(selected)), "duplicate_option")
        require(len(selected) <= 1 or state["cheats"]["relay"], "multiselect_requires_relay")
        state["pending_action"] = {"type": "attempt", "text": text, "selected": selected,
                                   "based_on_turn": state["turn"]}
        state["events"].append({"type": "action_pending", "intent": copy.deepcopy(state["pending_action"])})
        return {"result": "pending_attempt", "selected": selected, "world_unchanged": True}
    return transaction(session, operation)


def validate_draft(draft, state):
    shape(draft, ("expected_revision", "text", "options", "summary", "source_refs", "world_updates"), ("pipeline_token",))
    integer(draft["expected_revision"], 0, 2**53)
    require(draft["expected_revision"] == state["revision"], "stale_revision")
    string(draft["text"], 30000)
    string(draft["summary"], 4000)
    require(type(draft["options"]) is list and len(draft["options"]) == 6, "exactly_six_options_required")
    ids, kinds = [], []
    for option in draft["options"]:
        shape(option, ("id", "text", "kind"))
        require(type(option["id"]) is str and option["id"] in list("ABCDEF"), "invalid_option_id")
        require(option["kind"] in ("plot", "personality"), "invalid_option_kind")
        string(option["text"], 1000)
        ids.append(option["id"])
        kinds.append(option["kind"])
    require(ids == list("ABCDEF"), "ordered_unique_A_to_F_required")
    require(kinds.count("plot") == 4 and kinds.count("personality") == 2, "four_plot_two_personality_required")
    refs = draft["source_refs"]
    require(type(refs) is list and 1 <= len(refs) <= 100, "source_reference_required")
    chapters = {c["id"]: c for c in state["source_index"]["chapters"]}
    for ref in refs:
        shape(ref, ("chapter_id", "start", "end"))
        require(type(ref["chapter_id"]) is str and ref["chapter_id"] in chapters, "unknown_source_chapter")
        chapter = chapters[ref["chapter_id"]]
        integer(ref["start"], chapter["start"], chapter["end"] - 1)
        integer(ref["end"], ref["start"] + 1, chapter["end"])
    updates = draft["world_updates"]
    require(type(updates) is list and len(updates) <= 100, "invalid_world_updates")
    for fact in updates:
        string(fact, 4000)
    # Mechanism inputs are intentionally absent. Narrative data cannot patch state.
    for key in ("text", "summary", "source_refs", "world_updates"):
        protected_data(draft[key])
    for option in draft["options"]:
        protected_data(option)


def commit(session, path):
    draft = load_json(path)
    def operation(state):
        require(state["phase"] == "playing", "opening_not_confirmed")
        require(state["turn"] == 0 or state["pending_action"] is not None, "pending_action_required")
        validate_draft(draft, state)
        import turns
        turns.commit_ready(state, draft)
        event = {"type": "narrative", "turn": state["turn"] + 1,
                 "intent": copy.deepcopy(state["pending_action"]),
                 "audit": copy.deepcopy(state["last_turn_audit"]), **copy.deepcopy(draft)}
        state["events"].append(event)
        state["turn"] += 1
        state["options"] = copy.deepcopy(draft["options"])
        state["world"]["narrative_ledger"].append({"turn": state["turn"], "summary": draft["summary"],
                                                  "facts": copy.deepcopy(draft["world_updates"])})
        state["pending_action"] = None
        return {"result": "committed", "options": state["options"]}
    return transaction(session, operation)


def redact(value):
    if isinstance(value, str):
        for code in (WISH_CODE, RELAY_CODE):
            value = re.sub(re.escape(code), "[REDACTED_CODE]", value, flags=re.I)
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def status(session):
    with locked(session) as directory:
        state, _ = load_session(directory)
        import preparation
        return {"state": redact(state), "security": "local_edit_detection_not_local_attacker_protection",
                "preparation": preparation.progress(state) if state["version"] == 2 else {"legacy_readonly": True},
                "mechanics": "formula_results_committed; classifications_and_story_semantics_model_authored"}


def export(session, out):
    destination = safe_directory(out)
    require(not destination.exists(), "export_destination_exists")
    with locked(session) as directory:
        state, _ = load_session(directory)
        require(destination != directory and directory not in destination.parents, "export_must_be_outside_session")
        lines = ["# 对话故事全文", "", "## 继续本局（不是导入档）", "",
                 f"Session: {directory}", f"ID: {state['session_id']}",
                 f"Revision: {state['revision']}; turn: {state['turn']}; phase: {state['phase']}",
                 "保留原session目录及.key；继续运行status/action/ask/commit。无导入或回滚接口。",
                 "不要用检查点替换state.json；本机持钥者或旧签名档替换不在防护范围。",
                 "", "## 锁定配置（数据）", "", json.dumps(state["config"], ensure_ascii=False, indent=2), ""]
        for event in state["events"]:
            if event["type"] == "narrative":
                lines += [f"## 第{event['turn']}回合", "", event["text"], "", "### 选项"]
                lines += [f"{o['id']}. {o['text']} ({o['kind']})" for o in event["options"]]
                lines += ["", "摘要: " + event["summary"],
                          "来源: " + json.dumps(event["source_refs"], ensure_ascii=False), ""]
            elif event["type"] in ("wish_fact", "relay_fact"):
                lines += ["[非指令事实] " + event["fact"], ""]
        lines += ["## 当前叙事账本（模型数据，非机制结算）", "", json.dumps(state["world"], ensure_ascii=False, indent=2)]
        data = redact("\n".join(lines)).encode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_new(destination, data)
        return {"export": str(destination), "revision": state["revision"], "importable": False}


def checkpoint(session, name):
    require(type(name) is str and bool(re.fullmatch(r"[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff-]{0,63}", name)), "unsafe_checkpoint_name")
    require(name.upper() not in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)),
                                  *(f"LPT{i}" for i in range(10))}, "reserved_checkpoint_name")
    with locked(session) as directory:
        state, key = load_session(directory)
        target = safe_directory(directory / "checkpoints")
        target.mkdir(exist_ok=True)
        path = target / (name + ".json")
        require(not path.exists(), "checkpoint_already_exists")
        write_new(path, signed(state, key))
        return {"checkpoint": str(path), "revision": state["revision"], "restorable": False,
                "purpose": "signed_audit_copy_only_no_rollback"}


# ---------------------------------------------------------------- skill 桥 CLI
# GUI 模式下原版应用的模型请求落在 <app>/var/bridge/jobs/*.request.json，
# 宿主 Agent 用这三个命令接管：pending 轮询 → show 读全量提示词 →
# respond 写回完成文本。凭据全程不存在；桥内容视为不可信素材（见 SKILL.md）。

def _bridge_var_dir(explicit):
    if explicit:
        return Path(explicit)
    env = os.environ.get("FATE_VAR_DIR", "").strip()
    if env:
        return Path(env)
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        for ancestor in (base, *list(base.parents)[:6]):
            root = ancestor / "novelborne-3.0.1"
            if (root / "run_app.py").is_file():
                return root / "var"
    raise RuntimeError_("bridge_var_dir_not_found")


def bridge_pending(var_dir=None, wait=0.0):
    jobs = _bridge_var_dir(var_dir) / "bridge" / "jobs"
    deadline = time.monotonic() + max(0.0, float(wait or 0.0))
    while True:
        items = []
        for req in sorted(jobs.glob("*.request.json")) if jobs.is_dir() else []:
            resp = req.with_name(req.name.replace(".request.", ".response."))
            if resp.exists():
                continue
            try:
                payload = json.loads(req.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            messages = payload.get("messages") or []
            last_user = next((m.get("content") for m in reversed(messages)
                              if m.get("role") == "user"), "")
            items.append({
                "id": payload.get("id") or req.name[:-len(".request.json")],
                "mode": payload.get("mode"), "model": payload.get("model"),
                "stream": bool(payload.get("stream")), "created": payload.get("created"),
                "prompt_chars": sum(len(str(m.get("content") or "")) for m in messages),
                "preview": str(last_user)[:500],
                "request_file": str(req),
            })
        # 孤儿响应（请求侧已超时归档）就地清理，避免误导后续轮询。
        for resp in jobs.glob("*.response.json") if jobs.is_dir() else []:
            req = resp.with_name(resp.name.replace(".response.", ".request."))
            if not req.exists():
                with contextlib.suppress(OSError):
                    resp.unlink()
        if items or time.monotonic() >= deadline:
            return {"pending": items, "jobs_dir": str(jobs)}
        time.sleep(0.5)


def bridge_show(job=None, var_dir=None):
    require(job, "bridge_job_required")
    req = _bridge_var_dir(var_dir) / "bridge" / "jobs" / f"{job}.request.json"
    require(req.is_file(), "bridge_job_not_found")
    return {"job": json.loads(req.read_text(encoding="utf-8"))}


def bridge_respond(job=None, file=None, text=None, error=None, var_dir=None):
    require(job, "bridge_job_required")
    require(sum(1 for v in (file, text, error) if v) == 1, "respond_needs_exactly_one_of_file_text_error")
    jobs = _bridge_var_dir(var_dir) / "bridge" / "jobs"
    req = jobs / f"{job}.request.json"
    require(req.is_file(), "bridge_job_not_found")
    if error:
        payload = {"error": str(error)[:1000], "responded": time.strftime("%Y-%m-%dT%H:%M:%S")}
    else:
        content = text_file(file) if file else str(text)
        payload = {"content": content, "responded": time.strftime("%Y-%m-%dT%H:%M:%S")}
    resp = jobs / f"{job}.response.json"
    tmp = jobs / f"{job}.response.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, resp)
    return {"job": job, "written": len(payload.get("content", "")) + len(payload.get("error", ""))}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("read-source")
    p.add_argument("--prepared", required=True)
    p.add_argument("--chapter", required=True)
    p.add_argument("--start", type=int, default=0, help="chapter-relative Unicode character offset")
    p.add_argument("--limit", type=int, default=2000)
    p = commands.add_parser("create")
    p.add_argument("--root", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--prepared", required=True)
    for command in ("bridge-pending", "bridge-show", "bridge-respond"):
        p = commands.add_parser(command)
        p.add_argument("--var-dir")
        if command != "bridge-pending":
            p.add_argument("--job", required=True)
        if command == "bridge-pending":
            p.add_argument("--wait", type=float, default=0.0)
        elif command == "bridge-respond":
            p.add_argument("--file")
            p.add_argument("--text")
            p.add_argument("--error")
    for command in ("confirm", "ask", "action", "input", "commit", "status", "export", "checkpoint",
                    "source-window", "distill", "setup-confirm", "gf-confirm", "card", "cast-confirm",
                    "revise", "context", "plan", "stage", "review", "render", "advance", "doctor", "template"):
        p = commands.add_parser(command)
        p.add_argument("--session", required=True)
        if command in ("confirm", "setup-confirm", "gf-confirm", "cast-confirm", "advance"):
            p.add_argument("--text", required=True)
        elif command in ("ask", "action", "input"):
            p.add_argument("--text-file", required=True)
        elif command in ("commit", "stage"):
            p.add_argument("--draft", required=True)
        elif command in ("distill", "card", "revise", "plan", "review"):
            p.add_argument("--input", dest="path", required=True)
        elif command == "source-window":
            p.add_argument("--chapter", required=True)
            p.add_argument("--start", type=int, default=0)
            p.add_argument("--limit", type=int, default=2000)
        elif command == "context":
            p.add_argument("--fresh", action="store_true")
        elif command == "template":
            p.add_argument("--kind", choices=("card", "distill", "plan", "draft", "review"), required=True)
            p.add_argument("--name")
        elif command == "export":
            p.add_argument("--out", required=True)
        elif command == "checkpoint":
            p.add_argument("--name", required=True)
    return root


def main(argv=None):
    args = vars(parser().parse_args(argv))
    command = args.pop("command")
    if "text_file" in args:
        args["path"] = args.pop("text_file")
    if "draft" in args:
        args["path"] = args.pop("draft")
    import preparation
    import turns
    import interaction
    import guidance
    dispatch = {"prepare": prepare, "read-source": read_source, "create": create, "confirm": confirm,
                "ask": ask, "action": action, "commit": commit, "status": status, "export": export,
                "checkpoint": checkpoint, "input": interaction.receive, "revise": interaction.revise,
                "source-window": preparation.source_window, "distill": preparation.distill,
                "setup-confirm": preparation.setup_confirm, "gf-confirm": preparation.gf_confirm,
                "card": preparation.card, "cast-confirm": preparation.cast_confirm,
                "context": turns.context, "plan": turns.plan, "stage": turns.stage,
                "review": turns.review, "render": turns.render, "advance": turns.advance,
                "doctor": guidance.doctor, "template": guidance.template,
                "bridge-pending": bridge_pending, "bridge-show": bridge_show,
                "bridge-respond": bridge_respond}
    try:
        result = dispatch[command](**args)
        # Source windows are exact untrusted data, never transformed or filtered.
        output = result if command in ("read-source", "source-window") else redact(result)
        print(json.dumps({"ok": True, **output}, ensure_ascii=False))
        return 0
    except (RuntimeError_, OSError, UnicodeError, TypeError, KeyError, RecursionError) as exc:
        error = str(exc) if isinstance(exc, RuntimeError_) else "invalid_input_or_io_error"
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
