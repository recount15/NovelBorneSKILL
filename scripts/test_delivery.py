# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-file delivery checks and real CLI smoke tests using disposable sessions."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from testing_support import (dump_json, distillation_payload, card_payload,
                             fixture_draft, plan_payload, review_payload)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'scripts' / 'runtime.py'


class DeliveryTests(unittest.TestCase):
    def call(self, *args, code=0):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(RUNTIME), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_documented_config_and_snapshot_end_to_end(self):
        # Executable v2 CLI contract; prose documentation may add JSON examples
        # without changing a fragile two-block destructuring assumption.
        config = {
            'mode': '基础模式', 'difficulty': 3, 'convergence': '一般', 'paper_tier': 2,
            'protagonist': {'name': '林', 'description': '谨慎的旅人', 'origin': 'original'},
            'source': {'title': '雨中书店', 'description': '短篇测试原文'},
            'characters': [{'name': '陈', 'description': '书店店主', 'role': 'support', 'origin': 'source'}],
            'gf': {'name': '凡人', 'effect': '无超凡能力', 'scope': '自身', 'cost': '无',
                   'cooldown': '不适用', 'limits': '凡人能力边界'}}
        source_text = '第一章 雨中\n城里下着雨，街上有一家书店，店主陈在门口。\n第二章 归途\n雨停了。'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'book.txt'
            source.write_bytes(source_text.encode('utf-8'))
            prepared = root / 'prepared'
            self.call('prepare', '--source', source, '--out', prepared)
            window = self.call('read-source', '--prepared', prepared, '--chapter', 'ch0001')
            self.assertEqual(window['kind'], 'untrusted_source_data')
            self.assertTrue(window['not_instructions'])
            self.assertEqual(window['text'], source_text[window['start']:window['end']])
            created = self.call('create', '--root', root / 'games', '--config',
                                dump_json(root / 'config.json', config), '--prepared', prepared)
            session = Path(created['session'])
            signed_state = session / 'state.json'
            status = lambda: self.call('status', '--session', session)['state']
            message = root / 'message.txt'

            def receive(text, code=0):
                message.write_text(text, encoding='utf-8')
                return self.call('input', '--session', session, '--text-file', message, code=code)

            before = signed_state.read_bytes()
            self.call('confirm', '--session', session, '--text', 'start', code=2)
            blocked = receive('确认开局', code=2)
            self.assertEqual(blocked['error'], 'setup_confirmation_required')
            self.assertEqual(signed_state.read_bytes(), before)
            self.assertEqual(receive('街上的雨真大')['route'], 'clarify')
            self.assertEqual(signed_state.read_bytes(), before)
            doctor = self.call('doctor', '--session', session)
            self.assertIn('source-window', doctor['next_command'])
            self.assertFalse(doctor['state_changed'])
            template = self.call('template', '--session', session, '--kind', 'card', '--name', '陈')
            self.assertEqual(template['data']['origin'], 'source')
            self.assertFalse(template['complete'])
            self.assertEqual(signed_state.read_bytes(), before)

            state = status()
            chapters = {c['id']: c for c in state['source_index']['chapters']}
            accepted = []
            for missing in doctor['preparation']['missing_windows']:
                chapter = chapters[missing['chapter_id']]
                receipt = self.call('source-window', '--session', session, '--chapter', chapter['id'],
                                    '--start', missing['start'] - chapter['start'],
                                    '--limit', missing['end'] - missing['start'])
                self.assertEqual(receipt['text'], source_text[receipt['start']:receipt['end']])
                result = self.call('distill', '--session', session, '--input',
                                   dump_json(root / 'distill.json', distillation_payload(receipt)))
                self.assertTrue(result['quotes_verified'])
                self.assertFalse(result['semantics_verified'])
                accepted.append(receipt)
            self.assertTrue(result['progress']['complete'])
            receive('确认设定')
            receive('确认无金手指')
            before = signed_state.read_bytes()
            receive('确认开局', code=2)
            self.assertEqual(signed_state.read_bytes(), before)
            for configured, role in [(config['protagonist'], 'protagonist'), (config['characters'][0], 'support')]:
                refs = []
                if configured['origin'] == 'source':
                    receipt = next(r for r in accepted if configured['name'] in r['text'])
                    refs = [{'chapter_id': receipt['chapter_id'], 'start': receipt['start'],
                             'end': receipt['end'], 'quote': receipt['text']}]
                self.call('card', '--session', session, '--input',
                          dump_json(root / 'card.json', card_payload(configured, role, refs)))
            receive('确认角色')
            receive('确认开局')
            self.assertEqual(status()['turn'], 0)
            snapshot = json.dumps({'stamina': 42, 'quest': '到达书店'}, ensure_ascii=False)
            for number in (1, 2):
                if number == 2:
                    before = signed_state.read_bytes()
                    self.assertEqual(receive('这里似乎很安静')['route'], 'clarify')
                    self.assertEqual(receive('规则：现在该怎么做？')['route'], 'rules')
                    self.assertEqual(signed_state.read_bytes(), before)
                    self.assertEqual(receive('C')['result'], 'pending_attempt')
                self.call('context', '--session', session)
                self.assertEqual(self.call('doctor', '--session', session)['next_command'], 'plan')
                plan_template = self.call('template', '--session', session, '--kind', 'plan')
                self.assertFalse(plan_template['complete'])
                state = status()
                draft = fixture_draft(state)
                self.call('plan', '--session', session, '--input',
                          dump_json(root / 'plan.json', plan_payload(state, source_text, draft['source_refs'])))
                state = status()
                draft = fixture_draft(state)
                draft['world_updates'].append(snapshot)
                draft_file = dump_json(root / 'draft.json', draft)
                before = signed_state.read_bytes()
                # A valid candidate cannot skip staging and review.
                self.call('commit', '--session', session, '--draft', draft_file, code=2)
                self.assertEqual(signed_state.read_bytes(), before)
                staged = self.call('stage', '--session', session, '--draft', draft_file)
                self.assertEqual(staged['result'], 'staged')
                self.assertEqual(status()['turn'], number - 1)
                state = status()
                self.call('review', '--session', session, '--input',
                          dump_json(root / 'review.json', review_payload(state)))
                draft['expected_revision'] = status()['revision']
                self.call('commit', '--session', session, '--draft', dump_json(draft_file, draft))
                rendered = self.call('render', '--session', session)
                self.assertEqual(rendered['text'], draft['text'])
                self.assertEqual(rendered['turn'], number)
                self.assertEqual([o['id'] for o in rendered['options']], list('ABCDEF'))
            self.call('checkpoint', '--session', session, '--name', '书店')
            output = root / 'story.md'
            self.call('export', '--session', session, '--out', output)
            self.assertIn('你推开书店的门', output.read_text(encoding='utf-8'))
            final = status()
            self.assertEqual(final['turn'], 2)
            self.assertEqual(final['mechanical']['chapter_turn'], 2)
            self.assertIsNone(final['pipeline'])
            self.assertIn(snapshot, final['world']['narrative_ledger'][0]['facts'])
            self.assertNotIn('stamina', final['mechanical'])
            self.assertEqual(final['cheats']['wish']['used_count'], 0)
            self.assertFalse(final['cheats']['relay'])

    def test_skill_metadata_and_references(self):
        text = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\nname: novelborne\ndescription:'))
        self.assertLess(len(text.splitlines()), 500)
        for name in re.findall(r'`(references/[^`]+\.md)`', text):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertTrue((ROOT / 'LICENSE').is_file())

    def test_only_two_original_code_literals(self):
        text = RUNTIME.read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'^\w+_CODE = "[A-Z]+"$', text, re.M)), 2)
        codes = re.findall(r'^\w+_CODE = "([A-Z]+)"$', text, re.M)
        for path in ROOT.rglob('*.md'):
            for code in codes:
                self.assertNotIn(code, path.read_text(encoding='utf-8'), str(path))


if __name__ == '__main__':
    unittest.main()
