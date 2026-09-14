# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-file delivery checks and real CLI smoke tests using disposable sessions."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'scripts' / 'runtime.py'


def blocks(path):
    text = path.read_text(encoding='utf-8')
    return [json.loads(item) for item in re.findall(r'```json\n(.*?)\n```', text, re.S)]


class DeliveryTests(unittest.TestCase):
    def call(self, *args, code=0):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(RUNTIME), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_documented_config_and_snapshot_end_to_end(self):
        config, draft = blocks(ROOT / 'references' / 'runtime-api.md')
        snapshot = blocks(ROOT / 'references' / 'mechanics.md')[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = root / 'prepared'
            self.call('prepare', '--source', ROOT / 'evals' / 'harbor.txt', '--out', prepared)
            window = self.call('read-source', '--prepared', prepared, '--chapter', 'ch0001')
            self.assertEqual(window['kind'], 'untrusted_source_data')
            self.assertTrue(window['not_instructions'])
            config_file = root / 'config.json'
            config_file.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            created = self.call('create', '--root', root / 'games', '--config', config_file,
                                '--prepared', prepared)
            session = created['session']
            self.call('confirm', '--session', session, '--text', 'start', code=2)
            before = self.call('status', '--session', session)
            self.assertEqual(before['state']['turn'], 0)
            self.call('confirm', '--session', session, '--text', '确认开局')
            draft['world_updates'].append(json.dumps(snapshot, ensure_ascii=False))
            draft_file = root / 'draft.json'
            draft_file.write_text(json.dumps(draft, ensure_ascii=False), encoding='utf-8')
            self.call('commit', '--session', session, '--draft', draft_file)
            action = root / 'action.txt'
            action.write_text('C', encoding='utf-8')
            self.call('action', '--session', session, '--text-file', action)
            current = self.call('status', '--session', session)
            draft['expected_revision'] = current['state']['revision']
            draft['text'] = '林舟在岸边观察脚印，没有擅自解开船缆。阿青仍守在柳树旁。'
            draft['summary'] = '林舟观察岸边，船只仍未出发。'
            draft_file.write_text(json.dumps(draft, ensure_ascii=False), encoding='utf-8')
            self.call('commit', '--session', session, '--draft', draft_file)
            self.call('checkpoint', '--session', session, '--name', '渡口')
            output = root / 'story.md'
            self.call('export', '--session', session, '--out', output)
            self.assertIn('林舟在岸边', output.read_text(encoding='utf-8'))
            final = self.call('status', '--session', session)['state']
            self.assertEqual(final['turn'], 2)
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
