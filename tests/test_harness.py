import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pstack_opencodex.py"

# Skill folders cursor/plugins pstack added between 12d587d and 88d4751 (0.15.29).
ADDED_IN_0_15_29 = (
    "benchmark-checklist",
    "correct",
    "create-formal-verification-skill",
    "in-your-own-words",
    "ketchup",
    "maintain-formal-verification-skill",
    "poteto-help",
    "principle-explain-the-number",
    "sharpen",
)
NEGATION = re.compile(r"(?i)\b(?:never|not|no|don't|do not|without)\b")
# A "-fast" counts as forbidden only when a negation precedes it in the same clause.
NEGATED_FAST = re.compile(r"(?i)\b(?:never|not|don't|do not|without)\b[^,;.]*-fast")


def section(text, heading):
    """The body of a '## heading' section, up to the next '## ' heading."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        raise AssertionError(f"HARNESS.md has no '## {heading}' section")
    return match.group(1)


def bullets(text):
    """Top-level '- ' bullets of a section, each joined onto one line."""
    return [" ".join(item.split()) for item in re.split(r"(?m)^- ", text)[1:]]


def sentences(text):
    flat = " ".join(text.split())
    return [part for part in re.split(r"(?<=[.!?])\s+(?=[A-Z`$\[(\"'])", flat) if part]


class BuiltHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pstack-harness-test-")
        cls.dist = Path(cls.tmp.name).resolve() / "dist"
        result = subprocess.run([sys.executable, str(TOOL), "build", "--out", str(cls.dist)], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            cls.tmp.cleanup()
            raise AssertionError(f"build failed:\n{result.stdout}{result.stderr}")
        cls.harness = (cls.dist / "HARNESS.md").read_text()
        cls.readme = (ROOT / "README.md").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bullet(self, heading, predicate, what):
        found = [item for item in bullets(section(self.harness, heading)) if predicate(item)]
        self.assertEqual(len(found), 1, f"expected one '{heading}' bullet that {what}, found {found}")
        return found[0]

    def test_each_skill_added_in_0_15_29_has_a_skill_note(self):
        notes = section(self.harness, "Skill notes")
        for name in ADDED_IN_0_15_29:
            with self.subTest(skill=name):
                self.assertIn(f"`{name}`", notes)

    def test_every_quoted_subagent_type_in_built_skills_is_mapped(self):
        quoted = set()
        for path in (self.dist / "skills").rglob("*.md"):
            quoted.update(re.findall(r'subagent_type: "([^"]+)"', path.read_text()))
        self.assertIn("comment-sicko", quoted, "expected upstream's folder-named agent in no-comments")
        for value in sorted(quoted):
            with self.subTest(subagent_type=value):
                self.assertIn(f'subagent_type: "{value}"', self.harness)

    def test_every_dist_path_named_by_the_harness_exists(self):
        self.assertNotIn("{{", self.harness)
        paths = re.findall(re.escape(str(self.dist)) + r"/[^\s`\"'()<>]*", self.harness)
        self.assertTrue(paths)
        for raw in sorted(set(paths)):
            path = raw.rstrip(".,:;")
            if path.endswith("/...") or "<" in path:
                continue
            with self.subTest(path=path):
                self.assertTrue(Path(path).exists(), path)

    def test_subagent_effort_choice_adjusts_only_reasoning_effort(self):
        # pstack #613: "Pick each subagent's reasoning level and fast or standard speed for the job".
        rule = self.bullet("Subagents", lambda item: re.search(r"(?i)\bspeed\b", item), "maps the per-spawn choice")
        self.assertIn("poteto-mode", rule)
        parts = sentences(rule)
        self.assertTrue(
            any(re.search(r"(?i)\bonly\b.*`reasoning_effort`|`reasoning_effort`.*\bonly\b", s) for s in parts),
            "the rule must say reasoning_effort is the only setting it adjusts",
        )
        self.assertRegex(rule, r"(?i)\bclamp")
        self.assertIn("Models", rule, "clamping follows the Models section")
        fallback = [s for s in parts if re.search(r"(?i)\breject", s)]
        self.assertTrue(fallback, "the rule must say what to do when the spawn rejects the adjusted effort")
        self.assertTrue(any(re.search(r"(?i)\brole(?:'s)? value", s) for s in fallback), fallback)

    def test_subagent_speed_choice_is_dropped_and_fast_is_never_added(self):
        rule = self.bullet("Subagents", lambda item: re.search(r"(?i)\bspeed\b", item), "maps the per-spawn choice")
        self.assertTrue(
            any(re.search(r"(?i)\b(?:ignore|omit|drop|skip)\b.*\bspeed\b|\bno\b.*\bspeed\b", s) for s in sentences(rule)),
            "the rule must drop the speed half of the choice",
        )
        self.assertIn("-fast", rule, "the rule names the suffix it forbids")
        for sentence in sentences(self.harness):
            if "-fast" in sentence:
                with self.subTest(sentence=sentence):
                    self.assertEqual(len(re.findall(r"-fast", sentence)), len(NEGATED_FAST.findall(sentence)))

    def test_generated_project_skills_go_to_the_codex_skill_folder(self):
        rule = self.bullet("Skill notes", lambda item: ".agents/skills/" in item, "names the generated skill folder")
        for name in ("create-formal-verification-skill", "maintain-formal-verification-skill"):
            with self.subTest(skill=name):
                self.assertIn(f"`{name}`", rule)
        self.assertRegex(rule, r"\.agents/skills/[^/\s`]+/SKILL\.md")
        self.assertRegex(rule, r"(?i)`name`.*\bfolder")
        self.assertIn("`description`", rule)
        self.assertRegex(rule, r"(?i)\bby path\b|\bnew session\b")
        self.assertNotIn(".cursor/", rule)

    def test_ketchup_counts_from_the_last_message_the_user_typed(self):
        rule = self.bullet("Skill notes", lambda item: item.startswith("`ketchup`"), "covers ketchup")
        parts = sentences(rule)
        self.assertTrue(any(re.search(r"(?i)\blast\b.*\btyped\b|\btyped\b.*\blast\b", s) for s in parts), rule)
        others = [s for s in parts if re.search(r"wait_agent|(?i:subagent)", s)]
        self.assertTrue(others, "the rule must say which messages are not the user's")
        for sentence in others:
            with self.subTest(sentence=sentence):
                self.assertRegex(sentence, NEGATION)
        self.assertRegex(rule, r"(?i)notification")
        self.assertRegex(rule, r"(?i)\babsolute\b.*\bpath\b")
        self.assertIn("mermaid", rule)

    def test_cursor_only_names_from_the_new_skills_are_mapped(self):
        visualize = self.bullet("Tools pstack does not ship", lambda item: item.startswith("`/visualize`"), "maps /visualize")
        self.assertIn("mermaid", visualize)
        adapter = self.bullet("Where pstack lives", lambda item: "claude-code.md" in item, "covers the Claude Code adapter")
        self.assertTrue(
            any("Codex" in s and NEGATION.search(s) for s in sentences(adapter)),
            "the adapter bullet must say the adapter does not apply to Codex",
        )
        plugin = self.bullet("Where pstack lives", lambda item: ".cursor-plugin/plugin.json" in item, "covers the plugin-path search")
        self.assertIn(str(self.dist), plugin)
        correct = self.bullet("Skill notes", lambda item: item.startswith("`correct`"), "covers correct")
        self.assertIn("`AGENTS.md`", correct)

    def test_graphite_is_no_longer_required(self):
        for label, text in (("HARNESS.md", self.harness), ("README.md", self.readme)):
            for phrase in ("gt auth", "gt init", "authToken", "graphite/user_config"):
                with self.subTest(file=label, phrase=phrase):
                    self.assertNotIn(phrase, text)
        self.assertNotIn("Graphite (`gt`) for Orchestrate", self.readme)

    def test_readme_keeps_the_lock_file_name(self):
        self.assertIn("`UPSTREAM.lock`", self.readme)
        self.assertNotIn("`UPSTREAM`", self.readme)


if __name__ == "__main__":
    unittest.main()
