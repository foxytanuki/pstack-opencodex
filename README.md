# pstack-opencodex

[![CI](https://github.com/foxytanuki/pstack-opencodex/actions/workflows/ci.yml/badge.svg)](https://github.com/foxytanuki/pstack-opencodex/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Use [pstack](https://github.com/cursor/plugins/tree/main/pstack), Lauren Tan's agent workflows for Cursor, in Codex through [opencodex](https://github.com/lidge-jun/opencodex).

This repository keeps a pinned, unmodified copy of pstack and builds a Codex adaptation from a small overlay. The overlay maps tools, skill paths, and model settings, adds delegation diagnostics, and patches the worktree audit for Linux and Codex sessions.

This is an independent community adaptation. It is not an official Cursor, OpenAI, or opencodex project. It does not bundle opencodex or provide model access.

## Requirements

- Python 3.11 or later; the Python tools use only the standard library.
- Git and `patch` on your `PATH`.
- Codex configured through opencodex, with an available model catalog.
- Additional tools required by the workflow you choose: GitHub CLI (`gh`) for GitHub operations, Bun for pstack's TypeScript scripts, and Graphite (`gt`) for Orchestrate. Orchestrate also requires `gt auth` and `gt init`.

## Quick start

Clone the repository and build the skills:

```sh
git clone https://github.com/foxytanuki/pstack-opencodex.git
cd pstack-opencodex
python3 tools/pstack_opencodex.py build
```

Install into one project's skill directory. Replace `/path/to/your/project` with the project's actual path:

```sh
python3 tools/pstack_opencodex.py install --target /path/to/your/project/.agents/skills
```

For all projects, install into your user skill directory instead:

```sh
python3 tools/pstack_opencodex.py install --target ~/.agents/skills
```

The installer creates symlinks into `dist/skills/`. Keep this checkout in place and rebuild after moving it; generated harness instructions contain absolute paths. Existing real skill directories are protected, but existing symlinks with matching names are replaced.

Start a new Codex session, invoke `$setup-pstack` to choose models available in your catalog, then use `$poteto-mode` for a task. Model settings live in `~/.codex/pstack-models.md`, separately from Cursor's rules. If you use a custom `CODEX_HOME`, pass the corresponding settings and config paths explicitly when needed; the harness documents the default locations.

[overlay/pstack-models.example.md](overlay/pstack-models.example.md) shows the role format. Its model names are illustrative provider aliases, not a guarantee of availability. Adapt them to your catalog before copying the file. Panel roles that require different model families need suitable models from those families.

## Check models and delegation

Validate model names and reasoning levels:

```sh
python3 tools/pstack_opencodex.py check-models
```

If your Codex configuration uses `model_catalog_json`, pass that catalog's path with `check-models --catalog /absolute/path/to/catalog.json`. The runtime check below selects the configured catalog automatically.

Before delegating to a routed child such as Claude or Grok, run a read-only preflight with the actual parent model slug:

```sh
python3 tools/pstack_opencodex.py check-runtime --parent-model YOUR_PARENT_MODEL
```

Use `--profile NAME` when Codex uses a profile, and `--role "how explainer"` to check only the role being dispatched. You can repeat `--role`. Explicit file overrides are available through `--file`, `--catalog`, `--codex-config`, and `--opencodex-config`; `--json` produces a machine-readable report.

| Exit code | Status | Meaning |
| --- | --- | --- |
| 0 | `CONFIGURATION_OK` | No known blocking condition in the checked configuration; live delegation remains unverified. |
| 1 | `BLOCKED` | A disabled model, incompatible encrypted task transport, invalid input, or another known blocker. |
| 2 | `INCONCLUSIVE` | The active session format or route is unknown, settings conflict, or an experimental mitigation needs live verification. |

The tools do not contact providers or change configuration. `check-models` validates names and efforts and rejects models marked `disabled`; it does not verify authentication, quotas, transport, or live availability.

The active session's V1/V2 format is not inferred from disk settings. Pass `--session-surface v1` or `v2` only when you have observed it in the running client/session. Existing sessions can retain an older catalog after configuration changes. Follow opencodex's restart instructions and verify a minimal delegation in a fresh session.

A native ChatGPT V2 parent can produce encrypted tasks that routed children cannot read; see [opencodex issue #92](https://github.com/lidge-jun/opencodex/issues/92). If you encounter `unreadable_encrypted_agent_task`, retrying another Claude model in the same session will not fix that transport failure. Use a verified compatible path. Experimental plaintext delivery and task recovery are never enabled automatically.

## What the build changes

- Adds a pointer to `dist/HARNESS.md` at the start of each skill, except `principle-*` skills.
- Adds Codex's `allow_implicit_invocation: false` policy for upstream skills marked `disable-model-invocation: true`.
- Normalizes skill names to directory names such as `poteto-mode`.
- Applies the patches in `overlay/patches/`, stopping if a patch no longer applies.
- Excludes `make-bot-ui`, which depends on Cursor automations and Grok Bots.
- Includes both this project's and upstream pstack's MIT license notices in `dist/`.

The harness maps Cursor cloud-agent steps to local workers. Available tools and model-selection capabilities depend on your Codex/opencodex setup; this adaptation does not add missing client capabilities. See [overlay/HARNESS.md](overlay/HARNESS.md) for the complete mapping and fallback rules.

## Repository layout

| Path | Purpose |
| --- | --- |
| `UPSTREAM` | Source repository, subtree, and pinned commit. |
| `upstream/` | Unmodified copy of `cursor/plugins/pstack`. |
| `overlay/` | Harness instructions, patches, exclusions, and model example. |
| `tools/` | Build, install, synchronization, and diagnostic tools. |
| `tests/` | Runtime diagnostic tests using temporary configurations and catalogs. |
| `dist/` | Generated skills, harness, build metadata, and license notices; ignored by Git. |

## Update upstream

```sh
python3 tools/pstack_opencodex.py sync
git diff --stat upstream
python3 tools/pstack_opencodex.py build
python3 tools/pstack_opencodex.py check-models
python3 -m unittest discover -s tests -v
```

`sync` fetches the latest commit affecting pstack and prints changes since the previous pin. Use `sync --ref COMMIT_SHA` to select a specific version. Review the diff before committing. Keep `upstream/` unmodified; local adaptations belong in `overlay/` or `tools/`. `check-models` also reports role names removed or renamed upstream.

## Uninstall

```sh
python3 tools/pstack_opencodex.py uninstall --target /path/to/your/project/.agents/skills
# Or, for the user-wide install:
python3 tools/pstack_opencodex.py uninstall --target ~/.agents/skills
```

Uninstall removes only symlinks whose targets point into this checkout's `dist/` directory.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 tools/pstack_opencodex.py build
```

Tests cover V1/V2 compatibility, disabled models, configuration/session mismatches, experimental mitigations, CLI exit codes, and preservation of input settings. They use temporary files and do not contact providers. A passing suite does not establish live delegation compatibility.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License and credits

The adaptation is licensed under [MIT](LICENSE). Upstream pstack is copyright 2026 Lauren Tan and is included under its original [MIT license](upstream/LICENSE). Builds retain that notice as `dist/LICENSE.pstack` alongside this project's `dist/LICENSE`.

Thanks to [Lauren Tan (poteto)](https://github.com/poteto) for pstack and the [opencodex contributors](https://github.com/lidge-jun/opencodex) for the provider proxy.
