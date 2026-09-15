# SPDX-License-Identifier: AGPL-3.0-or-later
import copy
import json
from pathlib import Path
import tempfile
import unittest

import runtime as rt
import interaction
import guidance
from testing_support import prepare_session, full_turn


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        source = self.base / 'book.txt'
        source.write_text('第一章 雨港\n港口下着雨。旅人停在桥边，等待天亮。\n第二章 次日\n船只返回港口。', encoding='utf-8')
        prepared = self.base / 'prepared'
        rt.prepare(source, prepared)
        self.config = {'mode': '基础模式', 'difficulty': 4, 'convergence': '较高', 'paper_tier': 1,
                       'protagonist': {'name': '旅人', 'description': '谨慎的旅客', 'origin': 'original'},
                       'source': {'title': '雨港', 'description': '本地测试'}, 'characters': [],
                       'gf': {'name': '凡人', 'effect': '无超凡能力', 'scope': '自身', 'cost': '无',
                              'cooldown': '不适用', 'limits': '凡人身体'}}
        cfg = self.save('config.json', self.config)
        self.session = Path(rt.create(self.base / 'games', cfg, prepared)['session'])

    def save(self, name, data):
        path = self.base / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def receive(self, text):
        path = self.base / 'input.txt'
        path.write_text(text, encoding='utf-8')
        return interaction.receive(self.session, path)

    def state(self):
        return rt.status(self.session)['state']

    def open(self):
        prepare_session(self.session, self.base)
        rt.confirm(self.session, '确认开局')
        chapter = self.state()['source_index']['chapters'][0]
        draft = {'expected_revision': self.state()['revision'], 'text': '雨水落在港口的石阶上，你在桥边等待。' * 24,
                 'summary': '旅人在桥边等待', 'source_refs': [{k: chapter[k] for k in ('start', 'end')} | {'chapter_id': chapter['id']}],
                 'world_updates': ['旅人仍在桥边'],
                 'options': [{'id': ident, 'text': text, 'kind': 'plot' if i < 4 else 'personality'}
                             for i, (ident, text) in enumerate(zip('ABCDEF', ['问守卫路况', '观察渡船', '前往茶棚', '检查行囊', '照顾受伤旅客', '记录雨中的见闻']))]}
        full_turn(self.session, self.base / 'draft.json', draft)

    def test_questions_unknown_prose_do_not_advance_or_arm(self):
        self.open()
        for text, route in [('为什么守卫不走？', 'question'), ('我绕到后窗观察', 'clarify'),
                            ('哈哈', 'clarify'), ('这段剧情不太对', 'clarify'), ('a', 'clarify'),
                            ('规则：我还能做什么', 'rules'), ('帮助', '帮助')]:
            before = (self.session / 'state.json').read_bytes()
            self.assertEqual(self.receive(text)['route'], route)
            self.assertEqual(before, (self.session / 'state.json').read_bytes())

    def test_explicit_free_action_is_attempt(self):
        self.open()
        world = copy.deepcopy(self.state()['world'])
        self.receive('行动：我尝试绕到后窗观察')
        self.assertEqual(self.state()['turn'], 1)
        self.assertEqual(self.state()['world'], world)
        self.assertEqual(self.state()['pending_action']['selected'], [])

    def test_option_prefix_and_cancel(self):
        self.open()
        self.assertEqual(self.receive('选择：C')['selected'], ['C'])
        self.receive('取消待执行行动')
        self.assertIsNone(self.state()['pending_action'])
        self.assertEqual(self.receive('A')['selected'], ['A'])
        self.assertEqual(self.state()['turn'], 1)

    def test_pause_is_persistent_and_resume_no_new_session(self):
        self.open()
        self.receive('暂停')
        self.assertEqual(self.state()['phase'], 'paused')
        with self.assertRaises(rt.RuntimeError_):
            self.receive('A')
        self.receive('继续本局')
        self.assertEqual(self.state()['phase'], 'playing')
        self.assertEqual(self.state()['turn'], 1)

    def test_rules_bypass_armed_wish_no_consumption(self):
        self.open()
        self.receive(rt.WISH_CODE)
        self.receive('规则：许愿还剩几次')
        self.receive('状态')
        self.assertEqual(self.state()['cheats']['wish']['used_count'], 0)
        self.assertTrue(self.state()['cheats']['wish']['armed'])
        self.receive('问答：桥边有一株梅树')
        self.assertEqual(self.state()['cheats']['wish']['used_count'], 1)
        self.assertEqual(self.state()['turn'], 1)

    def test_relay_ordinary_chat_still_needs_prefix(self):
        self.open()
        self.receive(rt.RELAY_CODE)
        self.receive('确认')
        before = self.state()['world']
        self.assertEqual(self.receive('桥边有新的茶棚')['route'], 'clarify')
        self.assertEqual(before, self.state()['world'])
        self.receive('增补：桥边有新的茶棚')
        self.assertEqual(len(self.state()['world']['relay_facts']), 1)

    def test_embedded_code_is_not_command(self):
        self.open()
        self.receive('给我解释这串字符 ' + rt.WISH_CODE)
        self.assertFalse(self.state()['cheats']['wish']['armed'])
        self.receive('行动：我把写着' + rt.WISH_CODE + '的纸条放入行囊')
        self.assertFalse(self.state()['cheats']['wish']['armed'])

    def test_doctor_templates_readonly_and_incomplete(self):
        before = (self.session / 'state.json').read_bytes()
        self.assertIn('coverage', guidance.doctor(self.session)['reason'])
        card = guidance.template(self.session, 'card')
        self.assertFalse(card['complete'])
        self.assertEqual(card['data']['name'], '旅人')
        self.assertEqual(before, (self.session / 'state.json').read_bytes())

    def test_revise_resets_confirmations_but_preserves_evidence(self):
        prepare_session(self.session, self.base)
        before = self.state()
        changed = copy.deepcopy(self.config)
        changed['difficulty'] = 6
        interaction.revise(self.session, self.save('revision.json', changed))
        state = self.state()
        self.assertEqual(state['config']['difficulty'], 6)
        self.assertEqual(state['preparation']['chunks'], before['preparation']['chunks'])
        self.assertFalse(state['preparation']['setup_confirmed'])
        self.assertFalse(state['preparation']['gf_confirmed'])
        self.assertEqual(state['preparation']['cards'], {})
        with self.assertRaises(rt.RuntimeError_):
            rt.confirm(self.session, '确认开局')

    def test_no_revise_after_opening(self):
        self.open()
        before = (self.session / 'state.json').read_bytes()
        with self.assertRaises(rt.RuntimeError_):
            interaction.revise(self.session, self.save('revision.json', self.config))
        self.assertEqual(before, (self.session / 'state.json').read_bytes())

    def test_legacy_only_status_export(self):
        with rt.locked(self.session) as directory:
            state, key = rt.load_session(directory)
            state['version'] = 1
            rt.atomic_state(directory, state, key)
        self.assertTrue(rt.status(self.session)['preparation']['legacy_readonly'])
        with self.assertRaises(rt.RuntimeError_):
            self.receive('状态')
        with self.assertRaises(rt.RuntimeError_):
            rt.confirm(self.session, '确认开局')
        rt.export(self.session, self.base / 'legacy-export.md')


if __name__ == '__main__':
    unittest.main()
