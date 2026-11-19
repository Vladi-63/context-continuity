import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prompt_packet


class PromptPacketTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / 'tools').mkdir()
        (self.root / prompt_packet.ENTRY).touch()
        (self.root / prompt_packet.ROSTER).write_text(json.dumps({'test': 'target'}))

    def send(self, draft, thread='target'):
        return prompt_packet.hook({
            'hook_event_name': 'PreToolUse', 'tool_name': prompt_packet.SENDER,
            'cwd': str(self.root),
            'tool_input': {'threadId': thread, 'hostId': 'local', 'prompt': draft},
        })

    def test_rewrite_keeps_task_and_material(self):
        task = 'Задача\nПроверить хеш, сохранив ограничения.'
        data = 'строки отчёта\r\n' * 10_000
        output = self.send(f'{task}\r\n{prompt_packet.MARKER}\r\n{data}')
        args = output['hookSpecificOutput']['updatedInput']
        self.assertEqual(args['threadId'], 'target')
        self.assertEqual(args['hostId'], 'local')
        prompt = args['prompt']
        self.assertTrue(prompt.startswith(task + '\n\n'))
        self.assertLess(len(prompt.encode()), prompt_packet.PROMPT_LIMIT)
        self.assertNotIn('строки отчёта', prompt)
        path, = (self.root / 'reports/.context-prompt-materials').iterdir()
        self.assertEqual(path.read_bytes(), data.encode())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn(hashlib.sha256(data.encode()).hexdigest(), prompt)

    def test_large_unmarked_message_is_held_only_in_scope(self):
        oversized = 'ё' * (prompt_packet.PROMPT_LIMIT // 2 + 1)
        self.assertIsNone(self.send('Короткая задача'))
        self.assertIsNone(self.send(oversized, 'unregistered'))
        self.assertEqual(self.send(oversized)['decision'], 'block')
        self.assertFalse((self.root / 'reports').exists())

    def test_source_input_is_unchanged(self):
        source = self.root / 'report.txt'
        source.write_bytes(b'local source\r\n')
        prompt = prompt_packet.from_source(self.root, 'Check report', source)
        self.assertIn('"report.txt"', prompt)
        self.assertIn(hashlib.sha256(b'local source\r\n').hexdigest(), prompt)
        self.assertEqual(source.read_bytes(), b'local source\r\n')

    def test_new_project_and_nested_working_directory(self):
        (self.root / prompt_packet.ENTRY).unlink()
        (self.root / prompt_packet.ROSTER).unlink()
        config = self.root / prompt_packet.PROJECT_CONFIG
        config.write_text(json.dumps({'version': 1, 'thread_ids': ['target']}))
        nested = self.root / 'child'
        nested.mkdir()
        event = {'hook_event_name': 'SessionStart', 'cwd': str(nested)}
        result = prompt_packet.hook(event)
        self.assertIn('35%', result['hookSpecificOutput']['additionalContext'])
        self.assertIn('archives', result['hookSpecificOutput']['additionalContext'])
        config.unlink()
        self.assertIsNone(prompt_packet.hook(event))

    def test_composer_blocks_long_draft_before_submission(self):
        event = {'hook_event_name': 'UserPromptSubmit', 'cwd': str(self.root)}
        self.assertIsNone(prompt_packet.hook(dict(event, prompt='Short instruction')))
        self.assertEqual(prompt_packet.hook(dict(event, prompt='x' * 4097))['decision'], 'block')
        draft = f'Short instruction\n{prompt_packet.ENGLISH_MARKER}\nLong material'
        self.assertEqual(prompt_packet.hook(dict(event, prompt=draft))['decision'], 'block')
        self.assertFalse((self.root / 'reports').exists())
        response = self.send(draft)
        self.assertIn('SHA-256', response['hookSpecificOutput']['updatedInput']['prompt'])

    def test_history_defaults_to_one_turn_and_preserves_explicit_request(self):
        event = {'hook_event_name': 'PreToolUse', 'tool_name': prompt_packet.READER,
                 'cwd': str(self.root)}
        defaults = prompt_packet.hook(dict(event, tool_input={'threadId': 'target'}))
        args = defaults['hookSpecificOutput']['updatedInput']
        self.assertEqual((args['turnLimit'], args['maxOutputCharsPerItem'], args['includeOutputs']),
                         (1, 2000, False))
        explicit = dict(args, turnLimit=2, maxOutputCharsPerItem=20_000, cursor='known-turn')
        self.assertIsNone(prompt_packet.hook(dict(event, tool_input=explicit)))
        self.assertIsNone(prompt_packet.hook(dict(event, tool_input={'threadId': 'outside'})))
