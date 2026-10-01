# pstack on Codex through opencodex

pstack was written for Cursor. This file maps its tools, paths, and model names to Codex running through opencodex, and adds delegation compatibility checks. Follow pstack's steps with these runtime constraints. Explicit user instructions override both pstack and this file.

## Where pstack lives

- Skills: `{{PSTACK_DIST}}/skills/<name>/SKILL.md`. Codex hides most pstack skills from its automatic skill list, so when pstack routes to "the **how** skill" or "the **laziness-protocol** principle skill", open that file directly. A principle named without its prefix lives at `skills/principle-<name>/`.
- `pstack/skills/...` in pstack text means `{{PSTACK_DIST}}/skills/...`. For `git show origin/main:pstack/skills/<path>`, read `{{PSTACK_DIST}}/skills/<path>`.
- Subagent definitions: `{{PSTACK_DIST}}/agents/poteto-agent.md` and `{{PSTACK_DIST}}/agents/comment-sicko.md`.
- Skill folders: `.agents/skills/` in the repository for project skills such as a generated `verify-<app>`, and `~/.agents/skills/` for user skills.
- Cursor paths in pstack text map as follows. `.cursor/skills/` is `.agents/skills/`. `~/.cursor/skills/` is `~/.agents/skills/`, and Codex also reads `~/.codex/skills/`. `~/.cursor/plugins/` is `~/.codex/plugins/`. Project rules under `.cursor/rules/` are the repository's `AGENTS.md` files. `~/.cursor/projects/<slug>/agent-transcripts/` is covered under Transcripts. For worktrees under `.cursor/worktrees/`, use `git worktree list`, which finds worktrees wherever they live.

## Subagents

- `Task` means Codex's `spawn_agent`. Use the collaboration tools actually exposed by the session. In the desktop surface, `wait_agent` waits for mailbox updates; read the delivered messages and final answers to collect results. `send_message` sends a message without starting an idle agent, `followup_task` assigns more work and starts an idle agent, and `interrupt_agent` stops its current turn while keeping it available. Interruption is not closure. Use `send_input`, `wait`, or `close_agent` only on hosts that expose those tools; do not invent absent tools.
- Pass the prompt as `message`, and set `model` and `reasoning_effort` as described under Models. Drop `subagent_type`, `run_in_background`, and any other parameter Codex does not have. Codex subagents already run in the background.
- When this host only accepts model overrides with a partial or empty fork, use `fork_turns: "none"` for independent tasks and include their context explicitly. This controls history inheritance, not V1/V2 transport or encryption.
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
3. Match the model against the catalog selected by `check-runtime` from the client's config and profile. It uses `~/.codex/models_cache.json` only when no `model_catalog_json` is configured. Pass the same path to `check-models --catalog` when an override is active. Use an exact match first. Otherwise use the slug whose part after the last `/` matches the name, treating `.` and `-` as equal and preferring `anthropic/`. So `claude-opus-5-5` resolves to `anthropic/claude-opus-5-5`.
4. Clamp the effort to that entry's `supported_reasoning_levels`: the highest supported level at or below the requested one, or the lowest supported level when none is lower.
5. A value with no catalog match is a rejected entry. Follow the rejected-entry rule of the skill you are running.

Model families go by the name after the provider prefix. `anthropic/claude-*` is the `claude-*` family, `devin/grok-*` is `grok-*`, and `gpt-*` stays `gpt-*`. Any other name is its own family.

For `/setup-pstack`, detect models from the client's configured catalog (or `~/.codex/models_cache.json` when no override is configured), write each value as `<catalog slug>-<effort>`, and write `~/.codex/pstack-models.md` without frontmatter. Then run `python3 {{PSTACK_REPO}}/tools/pstack_opencodex.py check-models --catalog <selected-catalog-path>` and fix every line it reports. Run the delegation preflight before dispatching a worker.

## Delegation preflight

Before choosing a routed child such as Claude or Grok, run the read-only check below with the actual parent model. Pass `--profile` if the client uses a Codex profile, and `--role` to check only the role being dispatched. The checker honors `model_catalog_json` in the selected Codex config instead of assuming the cache is authoritative.

```sh
python3 {{PSTACK_REPO}}/tools/pstack_opencodex.py check-runtime --parent-model <actual-parent-model>
```

`check-models` checks names and reasoning efforts and rejects catalog entries marked `disabled`. It does not verify transport, authentication, quotas, or live availability. `check-runtime` reads configuration and catalog metadata without changing settings or contacting providers. Its exit codes are 0 for `CONFIGURATION_OK`, 1 for `BLOCKED`, and 2 for `INCONCLUSIVE`. Even exit 0 is not proof of successful live delegation.

The active session surface defaults to unknown. Specify `--session-surface v1` or `v2` only from observed client/session evidence. A disk setting, catalog pin, or `ocx v2 status` output is not such evidence. Existing Codex sessions can keep an older model catalog after synchronization or configuration changes. Use a fresh session after the documented Codex restart when testing a new transport setting; do not silently restart the user's session.

A native ChatGPT V2 parent can emit backend-encrypted task bodies that routed children cannot read ([opencodex issue #92](https://github.com/lidge-jun/opencodex/issues/92)). A child catalog entry being listed or eligible does not make that transport readable. If the checker blocks this combination, use a verified V1 session or an explicitly configured supported delivery path. Experimental plaintext delivery or task recovery only changes the result to inconclusive until a minimal live delegation confirms the task arrived and was executed. Never enable these settings automatically.

When compatibility is inconclusive, use compatible native workers for independent work if the user's scope permits it, and report any missing cross-family review. Do not represent a substitute from the same family as the required cross-family verdict.

Classify failures before applying pstack's rejected-model fallback rules:

- A rejected or absent model slug follows the skill's model-resolution rules.
- `unreadable_encrypted_agent_task` is a transport compatibility failure. Stop retrying equivalent routed children in that session; changing effort or `fork_turns` will not decrypt the body. Record the missing result and continue only through a known compatible path.
- Authentication failures, explicit HTTP 429, and timeouts keep their distinct observed classifications. A timeout alone is not evidence of 429 or an encryption failure. Report provider messages without credentials or task ciphertext.

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
