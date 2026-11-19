"""Enable Context Continuity for one local Work or Codex project."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from prompt_packet import PROJECT_CONFIG, RULES


KEY = 'model_post_turn_compact_threshold_percent'
SETTING = f'{KEY} = 35'
START = '<!-- context-continuity:start -->'
END = '<!-- context-continuity:end -->'
PRIVATE_MATERIALS = '/reports/.context-prompt-materials/'


def config_with_threshold(text):
    if text.strip() in ('', SETTING):
        return text if text.strip() else SETTING + '\n'
    try:
        import tomllib
    except ImportError as error:
        raise ValueError(f'For an existing TOML file, run setup with Python 3.11+ '
                         f'or set {SETTING} and use --keep-config.') from error
    values = tomllib.loads(text)
    if type(values.get(KEY)) is int and values[KEY] == 35:
        return text
    expected = {**values, KEY: 35}
    prefix = SETTING + '\n'
    if KEY in values:
        assignment = re.compile(r'(?m)^([ \t]*' + KEY + r'[ \t]*=[ \t]*)[+-]?[0-9_]+(?=[ \t]*(?:#|\r?$))')
        updated = assignment.sub(r'\g<1>35', text, count=1)
    else:
        updated = prefix + text
    if tomllib.loads(updated) != expected:
        raise ValueError(f'Set the top-level {SETTING} in .codex/config.toml and use --keep-config.')
    return updated


def read_text(path):
    if path.is_symlink():
        raise ValueError(f'Configure symlinked file manually: {path}')
    return path.read_bytes().decode('utf-8') if path.exists() else ''


def rules_in(text):
    rules = f'{START}\n{RULES.read_text(encoding="utf-8").strip()}\n{END}'
    if START not in text and END not in text:
        separator = '\n\n' if text.strip() else ''
        return text.rstrip('\n') + separator + rules + '\n'
    if text.count(START) != 1 or text.count(END) != 1 or text.index(END) < text.index(START):
        raise ValueError('Repair the Context Continuity markers in AGENTS.md before continuing.')
    begin = text.index(START)
    end = text.index(END) + len(END)
    return text[:begin] + rules + text[end:]


def write_changed(path, previous, updated):
    if previous == updated:
        return
    if read_text(path) != previous:
        raise ValueError(f'File changed during configuration: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(updated.encode('utf-8'))
            stream.flush()
            if path.exists():
                os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def configure(root, additional_ids, keep_config=False):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose an existing project directory.')
    config = root / '.codex/config.toml'
    if config.parent.is_symlink():
        raise ValueError('Configure the symlinked .codex directory manually.')
    agents = root / 'AGENTS.md'
    ignore = root / '.gitignore'
    marker = root / PROJECT_CONFIG
    previous = read_text(marker)
    project = json.loads(previous) if previous else {'version': 1, 'thread_ids': []}
    if not isinstance(project, dict) or project.get('version') != 1:
        raise ValueError('Invalid Context Continuity project configuration.')
    targets = project.get('thread_ids', [])
    if not isinstance(targets, list) or any(not isinstance(target, str) for target in targets):
        raise ValueError('Invalid Context Continuity thread IDs.')
    project['thread_ids'] = sorted(set(targets) | set(additional_ids))
    original_rules, original_ignore = read_text(agents), read_text(ignore)
    ignore_lines = original_ignore.splitlines()
    protected_ignore = original_ignore
    if PRIVATE_MATERIALS not in ignore_lines:
        protected_ignore = original_ignore.rstrip('\n') + ('\n' if original_ignore else '') + PRIVATE_MATERIALS + '\n'
    changes = [(agents, original_rules, rules_in(original_rules)),
               (ignore, original_ignore, protected_ignore),
               (marker, previous, json.dumps(project, indent=2) + '\n')]
    if not keep_config:
        existing = read_text(config)
        changes.insert(0, (config, existing, config_with_threshold(existing)))
    for path, old, new in changes:
        write_changed(path, old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--thread-id', action='append', default=[],
                        help='Register a local recipient for automatic handoffs; repeat for each ID.')
    parser.add_argument('--keep-config', action='store_true',
                        help=f'Keep your manually configured {SETTING}.')
    args = parser.parse_args()
    try:
        configure(args.project, args.thread_id, args.keep_config)
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    print(f'Enabled for {args.project.resolve()}. Review the Context Continuity hooks in the host.')


if __name__ == '__main__':
    main()
