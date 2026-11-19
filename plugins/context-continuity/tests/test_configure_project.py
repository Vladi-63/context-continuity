import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configure_project


class ConfigureProjectTest(unittest.TestCase):
    def test_idempotent_setup_preserves_project_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = root / 'AGENTS.md'
            agents.write_text('Existing project instructions.\n')
            configure_project.configure(root, ['second'])
            configure_project.configure(root, ['first', 'second'])
            self.assertTrue(agents.read_text().startswith('Existing project instructions.\n'))
            self.assertEqual(agents.read_text().count(configure_project.START), 1)
            self.assertEqual((root / '.codex/config.toml').read_text(),
                             configure_project.SETTING + '\n')
            marker = json.loads((root / '.context-continuity.json').read_bytes())
            self.assertEqual(marker['thread_ids'], ['first', 'second'])
            self.assertIn(configure_project.PRIVATE_MATERIALS, (root / '.gitignore').read_text())

    @unittest.skipUnless(importlib.util.find_spec('tomllib'), 'TOML editing uses Python 3.11+')
    def test_existing_toml_values_are_preserved(self):
        key = configure_project.KEY
        original = f'# keep\n{key} = 55 # existing\n[features]\nhooks = true\n'
        self.assertEqual(configure_project.config_with_threshold(original),
                         original.replace('55', '35'))
        nested = f'[profiles.test]\n{key} = 55\n'
        self.assertEqual(configure_project.config_with_threshold(nested),
                         configure_project.SETTING + '\n' + nested)
