import json,pathlib,unittest

class PackageLayoutTests(unittest.TestCase):
 def test_dispatch_hook_leaves_compaction_to_existing_host_guard(self):
  root=pathlib.Path(__file__).resolve().parents[1]
  manifest=json.loads((root/'.codex-plugin/plugin.json').read_text())
  self.assertNotIn('hooks',manifest)
  hooks=json.loads((root/'hooks/hooks.json').read_text())['hooks']
  self.assertEqual(set(hooks), {'SessionStart', 'UserPromptSubmit', 'PreToolUse'})
  self.assertEqual(hooks['PreToolUse'][0]['matcher'], '^mcp__codex_app__(send_message_to_thread|read_thread)$')
  self.assertIn('compact', hooks['SessionStart'][0]['matcher'].split('|'))
  self.assertTrue((root/'PROJECT_RULES.md').is_file())
  self.assertTrue((root/'skills/context-continuity/SKILL.md').is_file())

if __name__=='__main__':unittest.main()
