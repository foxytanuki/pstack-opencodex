# Contributing

Issues and pull requests are welcome. Include the command or workflow you used, the observed behavior, and the expected result. For delegation problems, include the diagnostic status and relevant model/catalog metadata, with credentials and private session content removed.

## Make a change

- Keep `upstream/` identical to the source pinned in `UPSTREAM`. Use the sync command to update it.
- Put harness instructions and patches in `overlay/`, and Python tooling in `tools/`.
- Keep `dist/` out of Git. It is generated and contains local absolute paths.
- Use English for project documentation and Conventional Commits for commit messages.
- Include behavioral tests for changes to model resolution or runtime diagnostics.

## Verify

Use Python 3.11 or later, Git, and `patch`:

```sh
python3 -m unittest discover -s tests -v
python3 tools/pstack_opencodex.py build
git diff --check
```

The tests run without provider access. For a change that affects actual delegation, describe any live verification separately from configuration checks.

Preserve both MIT notices when distributing the generated build: `dist/LICENSE` and `dist/LICENSE.pstack`.
