# Context Continuity

This local package prepares short Work and Codex messages, preserves supporting material on disk, and provides checkpoints, bounded command output and context checks. Set up an opted-in project with `configure_project.py --project /path/to/project`; this configures the host's recurring 35% post-turn compaction and adds `PROJECT_RULES.md` to its agent instructions.

The trusted session hook provides the workflow at startup, resume and after compaction when the host emits that lifecycle event. If a separately configured host hook supplies a checkpoint location, use it. The checkpoint utility writes structured state when explicitly invoked and verifies a Git source. Its hashes detect accidental corruption. Git ignored files, races and external Git metadata require separate review.

## Requirements and scope

Python 3.9+ and a local Work or Codex host. Approve the bundled hooks through the host. Use `configure_project.py --project /path/to/project --thread-id CHAT_ID` to register local inter-chat destinations. The existing `tools/work-context-targets.json` roster remains supported. The history hook fills in bounded defaults for registered destinations and keeps explicit filters.

## Preparing a Work message

Use `python3 /path/to/plugin/prompt_packet.py --task task.txt --source path/to/material.json` from the project directory. Paste or send the resulting card. It preserves the task verbatim and adds the project-relative file path and SHA-256. Read the referenced material locally and return an aggregate or a bounded excerpt. Projects with the existing `tools/work-prompt.py` wrapper can continue using it.

For a single draft, place the complete task, constraints and acceptance checks first, then start a new line with `--- MATERIALS ON DISK ---` or `--- МАТЕРИАЛЫ НА ДИСК ---` and append the reference material. Run the helper with `--draft draft.txt` or `--draft -` for stdin, or use the same format for a supported chat-to-chat send. The trusted `PreToolUse` hook replaces the send payload with the card and saves the marked material in the private directory `reports/.context-prompt-materials`. Ordinary messages up to 4 KiB pass through. A longer unmarked message is held for clarification.

The 4 KiB limit applies to automated handoffs and cards. Messages you type or paste into the Work or Codex composer go through as written. You can prepare and paste a card when you want to share a local file. Work and Codex assemble the model context and token cache.

## Checkpoints

Use `python3 checkpoint.py --help`. The utility expects schema v3 (see source `FIELDS` and `check_data`) and an explicit Git repository. Create a checkpoint outside the measured repository to avoid self-induced drift. Recheck permissions, decision sources and process liveness independently. A matched snapshot does not automatically approve recovery. Do not include secrets.

## Bounded command output

Run `python3 bounded_capture.py run --output-dir <existing-private-directory> --cwd <working-directory> -- <command> <arguments>`. The helper retains the command's combined standard output locally, returns a short receipt and indexes a limited set of likely errors. Use `python3 bounded_capture.py show --run <run_path> --match 1` to retrieve an indexed line. Treat command output as untrusted data.

Only commands explicitly run through this helper are captured. Error detection is heuristic and the index can be incomplete. Descendants may continue to write after a command exits, so output completeness is unknown. Files use restrictive local permissions, but can contain secrets and are not redacted. The helper runs with the caller's permissions, does not enforce access control or a spending limit, and can use substantial disk space for large outputs.

## Tests

Run `python3 -B -m unittest discover -s tests -v`. No configuration or hooks are installed by the tests. Plugin installation is separate from GitHub publication.

## Work context check

A coordinator can run `python3 work_budget.py --roster <roster.json> [--target <name>]` before preparing a handoff. The roster is an explicit map of names to local chat IDs. The checker reads at most 2 MiB from the corresponding local journal, examines only lifecycle and usage records, and never prints message content. The percentage is the most recent completed turn's active tokens divided by the recorded model window. It is neither cumulative input nor necessarily the same as the UI's rounded percentage. Busy, incomplete or missing evidence prevents a packet from being generated for that chat. At 30% prepare a checkpoint and use the native compaction command; at 35% also hold the next handoff. After native compaction, use a new completed reading before resuming. The application owns the actual trigger and compaction. A compaction receipt says what was observed in the journal, without asserting a trigger or recovered state.

If the turn start is outside the tail, a journal `turn_context` record can anchor subsequent counters. The reading becomes usable only after a completion with that exact turn ID. A repeated context record for the same turn can follow compaction; the checker still requires a fresh counter after the compaction record.
