import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pstack_opencodex.py"
PATCH_NAME = "0002-poteto-help-codex.patch"

INLINE_LINK = re.compile(r"\[[^\]]*\]\(<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+?)>?\s*$", re.MULTILINE)

# Pages the built poteto-help must route to: upstream's README and setup guide (the fix branch
# made them resolvable), its own references, and the skills its setup steps name.
REQUIRED_LINKS = {
    "../../README.md",
    "../../docs/guide/01-setup.md",
    "references/prompting.md",
    "references/recipes.md",
    "../poteto-mode/SKILL.md",
    "../setup-pstack/SKILL.md",
}


def markdown_links(path: Path) -> list[str]:
    text = path.read_text()
    return INLINE_LINK.findall(text) + REFERENCE_LINK.findall(text)


def local_markdown_links(path: Path) -> list[str]:
    local = []
    for target in markdown_links(path):
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith(("#", "/")):
            continue
        local.append(target.split("#", 1)[0])
    return [target for target in local if target]


def sentences(text):
    flat = " ".join(text.split())
    return [part for part in re.split(r"(?<=[.!?])\s+(?=[A-Z`$\[(\"'])", flat) if part]


class BuiltPotetoHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pstack-help-test-")
        cls.dist = Path(cls.tmp.name).resolve() / "dist"
        result = subprocess.run([sys.executable, str(TOOL), "build", "--out", str(cls.dist)], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            cls.tmp.cleanup()
            raise AssertionError(f"build failed:\n{result.stdout}{result.stderr}")
        cls.build_output = result.stdout
        cls.skill = cls.dist / "skills" / "poteto-help" / "SKILL.md"
        try:
            cls.text = cls.skill.read_text()
        except OSError:
            cls.tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_applies_the_poteto_help_patch(self):
        self.assertIn(f"applied {PATCH_NAME}", self.build_output)

    def test_every_local_link_in_the_built_skill_and_its_references_resolves(self):
        missing_routes = REQUIRED_LINKS - set(local_markdown_links(self.skill))
        self.assertEqual(missing_routes, set())
        files = [self.skill, *sorted((self.skill.parent / "references").glob("*.md"))]
        for path in files:
            with self.subTest(file=path.name):
                missing = [t for t in local_markdown_links(path) if not (path.parent / t).resolve().exists()]
                self.assertEqual(missing, [])

    def test_guide_pages_and_readme_are_the_unmodified_upstream_copies(self):
        self.assertEqual((self.dist / "README.md").read_bytes(), (ROOT / "upstream" / "README.md").read_bytes())
        upstream_docs = sorted(p for p in (ROOT / "upstream" / "docs").rglob("*") if p.is_file())
        self.assertTrue(upstream_docs)
        for source in upstream_docs:
            rel = source.relative_to(ROOT / "upstream")
            with self.subTest(file=str(rel)):
                self.assertEqual((self.dist / rel).read_bytes(), source.read_bytes())

    def test_claude_code_adapter_ships_unmodified_but_no_built_skill_links_to_it(self):
        adapter = Path("docs") / "harness" / "claude-code.md"
        self.assertEqual((self.dist / adapter).read_bytes(), (ROOT / "upstream" / adapter).read_bytes())
        shipped = (self.dist / adapter).resolve()
        routed = []
        for path in sorted((self.dist / "skills").rglob("*.md")):
            for target in markdown_links(path):
                local = target.split("#", 1)[0]
                # A public URL to the adapter routes there just as a relative link does.
                if local.endswith("harness/claude-code.md") or (local and (path.parent / local).resolve() == shipped):
                    routed.append(f"{path.relative_to(self.dist)} -> {target}")
        # Mentioning the adapter, for example to say it does not apply, is allowed; linking to it is not.
        self.assertEqual(routed, [])

    def test_excluded_make_bot_ui_is_not_linked_and_is_marked_unavailable(self):
        self.assertFalse((self.dist / "skills" / "make-bot-ui").exists())
        self.assertNotIn("make-bot-ui/SKILL.md", self.text)
        self.assertRegex(self.text, r"/make-bot-ui\` is not installed")

    def test_install_steps_keep_an_existing_skills_target(self):
        # dc0aa88: a new install defaults to ~/.agents/skills, but a user who already keeps
        # pstack skills in another folder, such as ~/.codex/skills, keeps that folder.
        steps = [line for line in self.text.splitlines() if "tools/pstack_opencodex.py install --target" in line]
        self.assertEqual(len(steps), 1, "expected one install step")
        parts = sentences(steps[0])
        self.assertTrue(any("install --target ~/.agents/skills" in s for s in parts), "a new install defaults to ~/.agents/skills")
        existing = [s for s in parts if "~/.codex/skills" in s]
        self.assertEqual(len(existing), 1, "one sentence covers an existing ~/.codex/skills target")
        rule = existing[0]
        self.assertRegex(rule, r"(?i)\balready\b", "the rule applies only when the user already has a skills folder")
        self.assertRegex(rule, r"(?i)\b(?:keep|reuse|use)\b.*\b(?:folder|target)\b")
        self.assertNotIn("~/.agents/skills", rule, "an existing target is not swapped for the default")
        self.assertNotRegex(rule, r"(?i)\b(?:migrat\w*|move|moving|switch\w*|replac\w*)\b")

    def test_setup_and_session_guidance_describes_codex(self):
        for codex in (
            "python3 tools/pstack_opencodex.py install --target",
            "~/.codex/pstack-models.md",
            "$setup-pstack",
            "$create-formal-verification-skill",
        ):
            with self.subTest(present=codex):
                self.assertIn(codex, self.text)
        self.assertRegex(self.text, r"(?i)\bCodex has no Custom Modes?\b")
        for cursor_only in (
            "/add-plugin pstack",
            "Customize in the sidebar",
            "~/.cursor/rules/pstack-models.mdc",
            "Use as Mode",
            "/plugin marketplace add",
            "/plugin install pstack@cursor-plugins",
            "`/setup-pstack` to type",
        ):
            with self.subTest(absent=cursor_only):
                self.assertNotIn(cursor_only, self.text)

    def test_a_new_session_is_told_how_to_resume_a_task(self):
        match = re.search(r"^## Start a task with.*?\n(.*?)(?=^## |\Z)", self.text, re.M | re.S)
        self.assertIsNotNone(match, "the 'Start a task' section is missing")
        parts = sentences(match.group(1))
        self.assertTrue(any(re.search(r"(?i)\bnew\b.*\bsession\b", s) for s in parts), "the section covers a new session")
        self.assertTrue(
            any(re.search(r"(?i)\b(?:resume|continue)\b", s) and "Session pickup" in s for s in parts),
            "the section routes resuming a task to the Session pickup playbook",
        )

    def test_routes_to_the_skills_added_upstream_are_kept(self):
        for name in ("in-your-own-words", "sharpen", "ketchup", "create-formal-verification-skill", "maintain-formal-verification-skill", "benchmark-checklist", "correct"):
            with self.subTest(skill=name):
                self.assertIn(f"](../{name}/SKILL.md)", self.text)


if __name__ == "__main__":
    unittest.main()
