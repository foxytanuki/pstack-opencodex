# pstack on Codex through opencodex

pstack was written for Cursor. This file maps its Cursor tools, paths, and model names to Codex running through opencodex on this machine. It changes names and locations only. Follow every pstack step as written. Explicit user instructions override both pstack and this file.

## Where pstack lives

- Skills: `{{PSTACK_DIST}}/skills/<name>/SKILL.md`. Codex hides most pstack skills from its automatic skill list, so when pstack routes to "the **how** skill" or "the **laziness-protocol** principle skill", open that file directly. A principle named without its prefix lives at `skills/principle-<name>/`.
- `pstack/skills/...` in pstack text means `{{PSTACK_DIST}}/skills/...`. For `git show origin/main:pstack/skills/<path>`, read `{{PSTACK_DIST}}/skills/<path>`.
- Subagent definitions: `{{PSTACK_DIST}}/agents/poteto-agent.md` and `{{PSTACK_DIST}}/agents/comment-sicko.md`.
- Skill folders: `.agents/skills/` in the repository for project skills such as a generated `verify-<app>`, and `~/.agents/skills/` for user skills.
- Cursor paths in pstack text map as follows. `.cursor/skills/` is `.agents/skills/`. `~/.cursor/skills/` is `~/.agents/skills/`, and Codex also reads `~/.codex/skills/`. `~/.cursor/plugins/` is `~/.codex/plugins/`. Project rules under `.cursor/rules/` are the repository's `AGENTS.md` files. `~/.cursor/projects/<slug>/agent-transcripts/` is covered under Transcripts. For worktrees under `.cursor/worktrees/`, use `git worktree list`, which finds worktrees wherever they live.

## Subagents

- `Task` means Codex's `spawn_agent`. Collect results with `wait_agent`, follow up with `send_input`, and finish with `close_agent`.
- Pass the prompt as `message`, and set `model` and `reasoning_effort` as described under Models. Drop `subagent_type`, `run_in_background`, and any other parameter Codex does not have. Codex subagents already run in the background.
- `readonly: true` means the prompt must say the agent may read files and run commands but must not edit files, commit, or push.
- `environment: "cloud"` means a local subagent that works in its own git worktree and output directory.
- `subagent_type: "poteto-agent"` means a subagent whose message starts with "Read {{PSTACK_DIST}}/skills/poteto-mode/SKILL.md in full, including its Principles section, before any work." Then give the task.
- `subagent_type: "Comment Sicko"` means a read-only subagent whose message starts with "Read {{PSTACK_DIST}}/agents/comment-sicko.md and follow it as your instructions."
- A pstack step that tells you to spawn subagents is the skill instruction that authorizes spawning. A model chosen in the pstack settings file is the user's explicit model choice.
- Codex can stop a subagent from spawning its own subagents (`agents.max_depth`). When a spawn fails for that reason, do those roles yourself, one after another, and say so in the report.

## Models

The settings file is `~/.codex/pstack-models.md`. It holds the same role lines as Cursor's `pstack-models.mdc` rule, without frontmatter. Wherever pstack names `~/.cursor/rules/pstack-models.mdc` or "the `pstack-models.mdc` rule", read this file. Leave `~/.cursor/rules/` alone, because Cursor on this machine owns it.

Resolve every model value, from the settings file or from a pstack default, in this order:

1. `inherit-parent` or `auto`: omit both `model` and `reasoning_effort`.
2. Split off the effort. The effort token is the last hyphen-separated token, or the one before a trailing `fast`: `low`, `medium`, `high`, `xhigh`, `max`, or `ultra`. Drop `fast`. `anthropic/claude-opus-5-5-max` becomes model `anthropic/claude-opus-5-5` with effort `max`. With no effort token, omit `reasoning_effort`.
3. Match the model against the Codex catalog, the `slug` values in `~/.codex/models_cache.json`. Use an exact match first. Otherwise use the slug whose part after the last `/` matches the name, treating `.` and `-` as equal and preferring `anthropic/`. So `claude-opus-5-5` resolves to `anthropic/claude-opus-5-5`.
4. Clamp the effort to that entry's `supported_reasoning_levels`: the highest supported level at or below the requested one, or the lowest supported level when none is lower.
5. A value with no catalog match is a rejected entry. Follow the rejected-entry rule of the skill you are running.

Model families go by the name after the provider prefix. `anthropic/claude-*` is the `claude-*` family, `devin/grok-*` is `grok-*`, and `gpt-*` stays `gpt-*`. Any other name is its own family.

For `/setup-pstack`, detect models from `~/.codex/models_cache.json`, write each value as `<catalog slug>-<effort>`, and write `~/.codex/pstack-models.md` without frontmatter. Then run `python3 {{PSTACK_REPO}}/tools/pstack_opencodex.py check-models` and fix every line it reports.

## Transcripts

Codex stores sessions at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, subagent sessions included. The first line is a `session_meta` record. Keep only files whose `payload.cwd` equals the workspace path, and never read other workspaces' sessions. To find the current session, check the newest candidates for the conversation's opening user prompt. If none matches, pass a digest of the session instead.

## Questions, goals, and loops

- `AskQuestion` means `request_user_input` when this session has it. Otherwise ask in chat with numbered options.
- `/goal` means Codex's `create_goal` when this session has it. Otherwise keep the objective and its exit condition in the plan file.
- `/loop` means a timed wait between checks: a shell `sleep` of at most 60 seconds per call, repeated. In the Codex desktop app, a thread heartbeat automation can wake the thread for longer intervals.

## Cursor features Codex does not have

- Cursor cloud agents and the Cursor dashboard. Codex subagents run on this machine and stop when Codex exits. Their state lives in `wait_agent` results, their worktrees, pushed branches, and the program's ledger files. Where pstack describes a Cursor restart, apply the same rule to a Codex restart: treat every subagent as gone and resume from those records. Where pstack offers a local root or a cloud root, follow the local root instructions.
- Cursor's built-in skills, such as its babysit skill. Codex has none of them, so follow the pstack playbook pstack names.
- Cursor automations, webhook routines, and Grok Bots. The `make-bot-ui` skill depends on them and is not installed.
- Graphite. Orchestrate's stack tools (`orch frontier`) run `gt` and read PR numbers through Graphite, which needs `gt auth` and `gt init` in the repository. Before starting Orchestrate, check `command -v gt` and check that `~/.config/graphite/user_config` contains an `authToken` key without printing its value, for example with `rg -q authToken ~/.config/graphite/user_config`. If `gt` is missing or not authenticated, tell the user before any work. The other playbooks use `gh` and never require `gt`.

## Tools pstack does not ship

- `create-skill`: use Codex's `$skill-creator`.
- `deslop` from `cursor-team-kit`: reread the diff before commit and remove AI slop yourself, applying the **unslop** skill's rules to prose.
- `control-ui`: the repository's own Playwright setup, or the `agent-browser` skill, for web and Electron apps.
- `control-cli`: a tmux session or a PTY command for CLIs and TUIs.
- Bugbot and Cursor's agentic security review: apply their triage rules to whatever review bots the repository uses. If none comment, skip those steps.
- MCP discovery in the **why** skill: Cursor's `mcps/` directory means the MCP tools in your own tool list, named `mcp__<server>__<tool>`. `codex mcp list` shows the configured servers.
