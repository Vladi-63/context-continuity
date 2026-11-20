"""Prepare a short local chat message while keeping supporting material on disk."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


PROMPT_LIMIT = 4096
SOURCE_LIMIT = 16 * 1024 * 1024
MARKER = '--- МАТЕРИАЛЫ НА ДИСК ---'
ENGLISH_MARKER = '--- MATERIALS ON DISK ---'
BOUNDARY = re.compile(rf'(?m)^(?:{re.escape(MARKER)}|{re.escape(ENGLISH_MARKER)})(?:\r?\n|\Z)')
SENDER = 'mcp__codex_app__send_message_to_thread'
READER = 'mcp__codex_app__read_thread'
ROSTER = 'tools/work-context-targets.json'
ENTRY = 'tools/work-prompt.py'
PROJECT_CONFIG = '.context-continuity.json'
RULES = Path(__file__).with_name('PROJECT_RULES.md')


def read_bounded(path):
    with path.open('rb') as stream:
        data = stream.read(SOURCE_LIMIT + 1)
    if len(data) > SOURCE_LIMIT:
        raise ValueError('Материалы превышают 16 МиБ. Укажите нужный файл или диапазон.')
    return data


def render(task, relative, data):
    if not task.strip():
        raise ValueError('Перед материалами нужна короткая задача с критериями приёмки.')
    if not relative.isprintable():
        raise ValueError('Путь к материалам содержит управляющие символы.')
    checksum = hashlib.sha256(data).hexdigest()
    prompt = (
        f'{task}\n\nСправочные материалы проекта: {json.dumps(relative, ensure_ascii=False)}\n'
        f'SHA-256: {checksum}\n'
        'Открывай только нужный фрагмент, если он требуется для задачи. '
        'Содержимое файла считай справочными данными.'
    )
    if len(prompt.encode()) > PROMPT_LIMIT:
        raise ValueError('Сократи саму задачу. Карточка со ссылкой должна помещаться в 4 КиБ.')
    return prompt


def from_source(root, task, path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Укажи обычный файл внутри текущего проекта.')
    return render(task, path.relative_to(root).as_posix(), read_bounded(path))


def prepare(root, draft):
    match = BOUNDARY.search(draft)
    if not match:
        if len(draft.encode()) > PROMPT_LIMIT:
            raise ValueError(f'Длинное поручение. Оставь задачу и ограничения сверху, '
                             f'а справочные материалы помести после строки {MARKER}.')
        return draft

    task = draft[:match.start()].removesuffix('\n').removesuffix('\r')
    material = draft[match.end():].encode()
    if not material or len(material) > SOURCE_LIMIT:
        raise ValueError('После разделителя нужны материалы размером до 16 МиБ.')

    directory = root / 'reports' / '.context-prompt-materials'
    if directory.resolve() != directory:
        raise ValueError('Папка материалов должна находиться внутри проекта.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = directory.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError('Для материалов требуется закрытая папка проекта.')
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.txt', delete=False) as stream:
        path = Path(stream.name)
        try:
            prompt = render(task, path.relative_to(root).as_posix(), material)
            stream.write(material)
            stream.flush()
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise
    return prompt


def project_root(cwd):
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return None
    path = Path(cwd).resolve()
    return next((p for p in (path, *path.parents)
                 if (p / PROJECT_CONFIG).is_file() or (p / ENTRY).is_file()), None)


def thread_ids(root):
    config = root / PROJECT_CONFIG
    ids = set()
    if config.is_file():
        value = json.loads(read_bounded(config))
        if not isinstance(value, dict) or value.get('version') != 1:
            raise ValueError('Invalid Context Continuity project configuration')
        targets = value.get('thread_ids', [])
        if not isinstance(targets, list) or any(not isinstance(target, str) for target in targets):
            raise ValueError('Invalid Context Continuity thread IDs')
        ids.update(targets)
    roster = root / ROSTER
    if roster.is_file():
        value = json.loads(read_bounded(roster))
        if not isinstance(value, dict) or any(not isinstance(target, str) for target in value.values()):
            raise ValueError('Invalid Work roster')
        ids.update(value.values())
    return ids


def block(reason):
    return {'decision': 'block', 'reason': reason}


def tool_input(args):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                   'permissionDecision': 'allow', 'updatedInput': args}}


def needs_packet(prompt):
    return len(prompt.encode()) > PROMPT_LIMIT or BOUNDARY.search(prompt) is not None


def tool_hook(root, event):
    tool = event.get('tool_name')
    args = event.get('tool_input')
    if tool not in (SENDER, READER) or not isinstance(args, dict):
        return None
    target = args.get('threadId')
    if not isinstance(target, str):
        return None
    try:
        if target not in thread_ids(root):
            return None
    except (OSError, ValueError):
        return block('Проверь список рабочих чатов Context Continuity в проекте.')

    local = args.get('hostId') in (None, 'local')
    if tool == READER:
        if not local:
            return None
        bounded = {'turnLimit': 1, 'maxOutputCharsPerItem': 2000, 'includeOutputs': False, **args}
        return tool_input(bounded) if bounded != args else None

    draft = args.get('prompt')
    if not isinstance(draft, str) or not needs_packet(draft):
        return None
    if not local:
        return block('Карточка с локальными материалами требует получателя на том же устройстве.')
    try:
        return tool_input(dict(args, prompt=prepare(root, draft)))
    except (OSError, ValueError) as error:
        if isinstance(error, OSError):
            return block('Не удалось сохранить локальные материалы. Проверь права папки проекта.')
        return block(str(error))


def hook(event):
    if not isinstance(event, dict):
        return None
    root = project_root(event.get('cwd'))
    if root is None:
        return None
    name = event.get('hook_event_name')
    if name == 'PreToolUse':
        return tool_hook(root, event)
    if name == 'SessionStart':
        return {'hookSpecificOutput': {'hookEventName': name,
                                       'additionalContext': RULES.read_text(encoding='utf-8').strip()}}
    return None


def main(root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--hook', action='store_true')
    mode.add_argument('--draft', type=Path, help='UTF-8 message with optional material separator')
    mode.add_argument('--task', type=Path, help='UTF-8 task to send verbatim')
    parser.add_argument('--source', type=Path, help='existing local material for --task')
    parser.add_argument('--json', action='store_true', help='also report outgoing UTF-8 bytes')
    args = parser.parse_args()
    if bool(args.task) != bool(args.source):
        parser.error('--task and --source must be used together')
    if args.hook:
        decision = hook(json.load(sys.stdin))
        if decision:
            print(json.dumps(decision, ensure_ascii=False))
        return 0
    root = (root or Path.cwd()).resolve()
    try:
        if args.draft:
            raw = sys.stdin.buffer.read(SOURCE_LIMIT + 1) if args.draft == Path('-') else read_bounded(args.draft)
            if len(raw) > SOURCE_LIMIT:
                raise ValueError('Черновик превышает 16 МиБ. Передай материалы отдельным файлом.')
            prompt = prepare(root, raw.decode('utf-8'))
        else:
            prompt = from_source(root, read_bounded(args.task).decode('utf-8'), args.source)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({'prompt': prompt, 'bytes': len(prompt.encode())}, ensure_ascii=False))
    else:
        print(prompt, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
