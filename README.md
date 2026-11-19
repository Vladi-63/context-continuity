# Context Continuity

**Keep AI chats focused across large projects.**

Context Continuity is a local plugin for ChatGPT Work and Codex. When work spans several chats, full manifests, logs, and other reference files can make even a small handoff expensive. Context Continuity keeps those materials on disk and delivers a compact task card with the instructions, a file path, and a SHA-256 checksum. The receiving chat can open the specific material it needs.

## A real handoff

| Original task and inline materials | Task card delivered |
| ---: | ---: |
| 101,936 tokens | **319 tokens** |

That is **99.7% fewer tokens in the handoff text**. In this test, the sending chat invoked the plugin's handler before dispatch. The receiving chat completed the requested file verification using the card and the local reference. Counts use `o200k_base`. The application's model requests also include the receiving chat's active history and instructions.

## How it works

- **Task cards.** Keep the goal, constraints, and acceptance checks in the message. Put long supporting material after the separator so the handler can turn it into a local file reference.
- **Native compaction at 35%.** On an opted-in local project, the host compacts active chat history after a final answer when it reaches 35% of the usable context window. Project instructions preserve a short handoff with the current revision and next action.
- **Focused lookups.** Registered chat lookups default to one turn, and the command output helper lets you inspect indexed lines from logs stored locally.

## Install

Use the local Work or Codex runtime on macOS or Linux and a version of the Codex CLI with `codex plugin` support. The runtime scripts use Python 3.9+. Use Python 3.11+ to merge an existing complex TOML configuration.

Clone this repository using GitHub's **Code** menu or unpack the ZIP from **Releases**. Open a terminal in the folder that contains this README and run:

```sh
codex plugin marketplace add "$PWD"
codex plugin add context-continuity@context-continuity-local
python3 -B plugins/context-continuity/configure_project.py --project "/path/to/project"
```

Replace `/path/to/project` with the project you want to configure. The setup script writes or preserves the top-level `model_post_turn_compact_threshold_percent = 35` in the project's `.codex/config.toml`, adds the workflow to `AGENTS.md`, opts the project into the plugin's handlers, and excludes saved materials from Git. If you manage the configuration by hand, set the same key and pass `--keep-config`. The host must trust the selected project configuration.

Review and approve the three **Context Continuity** hooks in the host. A new or resumed local chat can load the rules. Existing chats can require the host to reload the plugin. For a user-level policy across trusted local projects, place the same compaction key in the user-level configuration and opt each project into the hooks with the setup command.

For supported chat-to-chat sends, repeat the setup command with `--thread-id CHAT_ID` for each local destination, using its chat ID. Projects with an existing `tools/work-context-targets.json` and migration setup keep those destinations. Use the setup command again when you need to register a new chat.

You can also add the GitHub repository as a marketplace using `codex plugin marketplace add OWNER/REPO --ref v0.3.0`, replacing `OWNER/REPO` with this repository's owner and name. Keep a local checkout or unpacked release to run the project setup script.

## Use

| What you do | What happens |
| --- | --- |
| Work on a task | The project rules keep the current assignment and next action short and direct the chat to relevant source ranges. The host compacts active history after a final response at 35% of usable context. |
| Send a task from one registered local project chat to another | Put task and acceptance criteria first, then `--- MATERIALS ON DISK ---` (or `--- МАТЕРИАЛЫ НА ДИСК ---`) on its own line and paste the reference material below. The hook sends the task, relative path and SHA-256. Short unmarked text passes through. An unmarked message above 4 KiB is held for clarification. |
| Type directly into the Work or Codex composer | Prepare the card below and paste its result. On supported hosts the submit hook stops an oversized or still-marked draft before it reaches the model. The composer hook API exposes blocking and extra context. |
| Look up a recent chat turn | Standard lookups of registered destinations default to one turn, up to 2,000 characters per item, with tool output excluded. A caller can explicitly request a specific older turn or larger item. |

```sh
cd "/path/to/project"
plugin="/absolute/path/to/this/repository/plugins/context-continuity"
python3 -B "$plugin/prompt_packet.py" --task task.txt --source data/report.json
# Or prepare a marked draft in one file.
python3 -B "$plugin/prompt_packet.py" --draft draft.txt
# For Codex CLI, pass the prepared card on stdin.
python3 -B "$plugin/prompt_packet.py" --draft draft.txt > short-card.txt &&
  codex exec - < short-card.txt
```

The source remains local. The card preserves task instructions verbatim. It asks the recipient to inspect only what the task needs. A marked inline source is saved under `reports/.context-prompt-materials/` with restrictive file permissions. Check the target can access the same project before sharing local references.

The plugin does not require separate API credentials. Its scripts run locally. The host submits model requests according to its own settings when you send a card or the model reads materials.

The 4 KiB cap applies to the text of the card. The host controls its active model context, earlier messages, caching and compaction. A large turn can pass 35% while it runs. Cloud-orchestrated or synced Work may have different hook capabilities, and local files and commands require a local runtime. See the official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference#model_post_turn_compact_threshold_percent), [hooks](https://learn.chatgpt.com/docs/hooks) and [plugin compatibility](https://learn.chatgpt.com/docs/plugins).

## Run the tests

```sh
python3 -B -m unittest discover -s plugins/context-continuity/tests
```

Use Python 3.11 or later to exercise every test, including merging an existing TOML configuration.

See [the plugin reference](plugins/context-continuity/README.md) for checkpoints, bounded logs and context checks.

## License

[MIT](LICENSE)
