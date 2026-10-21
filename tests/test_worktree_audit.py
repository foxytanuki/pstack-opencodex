import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pstack_opencodex.py"
SCRIPT = Path("skills") / "poteto-mode" / "scripts" / "worktree-audit.sh"
PATCH_NAME = "0001-worktree-audit-linux-and-codex.patch"
DAY = 86400


def build_into(root):
    dist = root / "dist"
    result = subprocess.run([sys.executable, str(TOOL), "build", "--out", str(dist)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(f"build failed:\n{result.stdout}{result.stderr}")
    return dist, result.stdout


def day(timestamp):
    return time.strftime("%Y-%m-%d", time.gmtime(timestamp))


class BuiltWorktreeAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in ("bash", "patch") if shutil.which(tool) is None]
        if missing:
            raise unittest.SkipTest(f"missing tools: {', '.join(missing)}")
        cls.tmp = tempfile.TemporaryDirectory(prefix="pstack-audit-test-")
        cls.root = Path(cls.tmp.name).resolve()
        try:
            dist, cls.build_output = build_into(cls.root)
        except AssertionError:
            cls.tmp.cleanup()
            raise
        cls.script = dist / SCRIPT
        cls.text = cls.script.read_text()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_applies_the_worktree_audit_patch(self):
        self.assertIn(f"applied {PATCH_NAME}", self.build_output)

    def test_built_script_parses(self):
        result = subprocess.run(["bash", "-n", str(self.script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_runs_outside_a_repository(self):
        outside = self.root / "outside"
        outside.mkdir(exist_ok=True)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(outside)}
        result = subprocess.run(["bash", str(self.script), "--help"], cwd=outside, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: worktree-audit.sh [-b|--base <ref>] [repo-path]", result.stdout)
        self.assertNotIn("set -u", result.stdout)

    def test_patch_keeps_upstream_base_handling(self):
        for marker in ("-b|--base)", 'echo "# base: $base"', 'git merge-base --is-ancestor "$head" "$base"', "*/open|*/draft"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_patch_adds_codex_rollouts_and_gnu_bsd_portability(self):
        markers = (
            '"${CODEX_HOME:-$HOME/.codex}/sessions"',
            "-name 'rollout-*.jsonl' -mtime -30",
            "stat -c '%Y %n'",
            "stat -f '%m %N'",
            'date -d "@$1"',
            'date -r "$1"',
            'rm -f "$prs" "$codex_sessions"',
        )
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)
        self.assertNotIn("| xargs stat -f '%m %N' 2>/dev/null | sort -rn", self.text)


class WorktreeAuditLastChat(unittest.TestCase):
    """Run the patched audit on a throwaway repository with fake Codex and Cursor transcripts.

    HOME, CODEX_HOME, and PATH point into a temporary directory. Stub gh and origin
    commands fail, so the audit never reads real credentials or contacts a forge.
    """

    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in ("bash", "git", "patch", "rg", "jq") if shutil.which(tool) is None]
        if missing:
            raise unittest.SkipTest(f"missing tools: {', '.join(missing)}")
        cls.tmp = tempfile.TemporaryDirectory(prefix="pstack-audit-run-")
        cls.root = Path(cls.tmp.name).resolve()
        try:
            cls.prepare()
        except BaseException:
            cls.tmp.cleanup()
            raise

    @classmethod
    def prepare(cls):
        dist, _ = build_into(cls.root)
        home, codex_home, stubs = cls.root / "home", cls.root / "codex-home", cls.root / "bin"
        for path in (home, codex_home, stubs):
            path.mkdir()
        for tool in ("gh", "origin"):
            stub = stubs / tool
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)
        env = {
            "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "pstack test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "pstack test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "TZ": "UTC",
            "LC_ALL": "C",
        }

        def git(*args):
            subprocess.run(["git", *args], env=env, check=True, capture_output=True, text=True, timeout=30)

        main = cls.root / "repo"
        git("init", "-q", str(main))
        git("-C", str(main), "symbolic-ref", "HEAD", "refs/heads/main")
        git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "init")
        cls.worktrees = {name: cls.root / name for name in ("feature", "feature-2", "feature-3")}
        for name, path in cls.worktrees.items():
            git("-C", str(main), "worktree", "add", "-q", "-b", name, str(path))

        now = time.time()
        cls.codex_ts = int(now - 2 * DAY)
        cls.cursor_ts = int(now - 10 * DAY)
        sessions = codex_home / "sessions" / "2026" / "10" / "19"
        sessions.mkdir(parents=True)
        recent = sessions / "rollout-recent.jsonl"
        recent.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": str(cls.worktrees["feature-2"])}}) + "\n")
        os.utime(recent, (cls.codex_ts, cls.codex_ts))
        stale = sessions / "rollout-stale.jsonl"
        stale.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": str(cls.worktrees["feature-3"])}}) + "\n")
        os.utime(stale, (now - 40 * DAY, now - 40 * DAY))
        slug = str(main).lstrip("/").replace("/", "-")
        transcripts = home / ".cursor" / "projects" / slug / "agent-transcripts"
        transcripts.mkdir(parents=True)
        chat = transcripts / "chat.jsonl"
        chat.write_text(json.dumps({"path": f"{cls.worktrees['feature']}/src/app.ts"}) + "\n")
        os.utime(chat, (cls.cursor_ts, cls.cursor_ts))

        cls.result = subprocess.run(["bash", str(dist / SCRIPT), "-b", "main", str(main)], cwd=main, env=env, capture_output=True, text=True, timeout=120)
        cls.rows = {}
        for line in cls.result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) == 9 and fields[0] != "SIZE":
                cls.rows[fields[8]] = fields

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def row(self, name):
        return self.rows[str(self.worktrees[name])]

    def test_audit_lists_every_worktree_against_the_explicit_base(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertIn("# base: main", self.result.stdout)
        self.assertEqual(set(self.rows), {str(path) for path in self.worktrees.values()})

    def test_recent_codex_rollout_sets_last_chat(self):
        self.assertEqual(self.row("feature-2")[6], day(self.codex_ts))
        self.assertEqual(self.row("feature-2")[7], "verify-recent-chat")

    def test_cursor_transcripts_still_count_and_path_prefixes_do_not_match(self):
        # feature-2's newer rollout must not leak into feature, whose path is a prefix of it.
        self.assertEqual(self.row("feature")[6], day(self.cursor_ts))

    def test_rollouts_older_than_30_days_are_ignored(self):
        self.assertEqual(self.row("feature-3")[6], "-")


if __name__ == "__main__":
    unittest.main()
