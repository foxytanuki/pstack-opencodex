import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pstack_opencodex.py"
sys.path.insert(0, str(ROOT / "tools"))
import pstack_opencodex  # noqa: E402

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
EXPLICIT_ONLY_POLICY = "policy:\n  allow_implicit_invocation: false\n"


def excluded_skills():
    lines = (ROOT / "overlay" / "exclude").read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def upstream_skills():
    return {p.name for p in (ROOT / "upstream" / "skills").iterdir() if (p / "SKILL.md").exists()}


def frontmatter(path):
    front, _ = pstack_opencodex.split_frontmatter(path.read_text())
    return front


def build(out):
    result = subprocess.run([sys.executable, str(TOOL), "build", "--out", str(out)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(f"build failed:\n{result.stdout}{result.stderr}")
    return result


class BuiltSkills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pstack-build-test-")
        # Resolve symlinked temp roots (macOS /var -> /private/var) so paths match the build output.
        cls.dist = Path(cls.tmp.name).resolve() / "dist"
        try:
            cls.result = build(cls.dist)
        except AssertionError:
            cls.tmp.cleanup()
            raise
        cls.info = json.loads((cls.dist / "BUILD-INFO.json").read_text())
        cls.built = {p.name for p in (cls.dist / "skills").iterdir() if (p / "SKILL.md").exists()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_ships_every_upstream_skill_except_the_exclusions(self):
        self.assertEqual(self.built, upstream_skills() - excluded_skills())
        self.assertEqual(set(self.info["excluded"]), excluded_skills())
        self.assertNotIn("make-bot-ui", self.built)

    def test_build_reports_how_many_skills_it_ships(self):
        count = len(upstream_skills() - excluded_skills())
        self.assertEqual(self.info["skills"], count)
        self.assertIn(f"built {count} skills into {self.dist}", self.result.stdout)

    def test_skills_added_in_0_15_29_are_built_with_the_harness_pointer(self):
        pointer = f"read {self.dist}/HARNESS.md"
        for name in ADDED_IN_0_15_29:
            with self.subTest(skill=name):
                skill_md = self.dist / "skills" / name / "SKILL.md"
                self.assertTrue(skill_md.exists(), f"{name} was not built")
                if name.startswith("principle-"):
                    self.assertNotIn(pointer, skill_md.read_text())
                else:
                    self.assertIn(pointer, skill_md.read_text())

    def test_each_built_skill_is_named_after_its_folder(self):
        for name in sorted(self.built):
            with self.subTest(skill=name):
                front = frontmatter(self.dist / "skills" / name / "SKILL.md")
                names = [line.split(":", 1)[1].strip() for line in front if line.startswith("name:")]
                self.assertEqual(names, [name])

    def test_explicit_only_policy_follows_upstream_frontmatter(self):
        explicit = 0
        for name in sorted(self.built):
            with self.subTest(skill=name):
                upstream_front = frontmatter(ROOT / "upstream" / "skills" / name / "SKILL.md")
                flagged = "disable-model-invocation: true" in [line.strip() for line in upstream_front]
                meta = self.dist / "skills" / name / "agents" / "openai.yaml"
                self.assertEqual(meta.exists(), flagged)
                if flagged:
                    self.assertEqual(meta.read_text(), EXPLICIT_ONLY_POLICY)
                explicit += flagged
        self.assertEqual(self.info["explicit_only"], explicit)

    def test_upstream_plugin_manifests_are_not_shipped(self):
        self.assertFalse((self.dist / "plugin.json").exists())
        self.assertFalse((self.dist / ".cursor-plugin").exists())

    def test_both_license_notices_are_shipped(self):
        self.assertEqual((self.dist / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
        self.assertEqual((self.dist / "LICENSE.pstack").read_bytes(), (ROOT / "upstream" / "LICENSE").read_bytes())


class SkillNameNormalization(unittest.TestCase):
    """Upstream names every skill after its folder since #702. The build keeps its existing
    normalization as a safety net: a no-op for matching names, a rewrite for a future mismatch."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pstack-name-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def skill(self, folder, name):
        skill_dir = self.root / "skills" / folder
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\ndisable-model-invocation: true\n---\n\n# Test\n"
        )
        return skill_dir

    def test_a_name_that_differs_from_the_folder_is_rewritten_to_the_folder(self):
        skill_dir = self.skill("poteto-mode", "Poteto Mode")
        self.assertTrue(pstack_opencodex.adapt_skill(skill_dir, self.root))
        front = frontmatter(skill_dir / "SKILL.md")
        self.assertEqual([line for line in front if line.startswith("name:")], ["name: poteto-mode"])

    def test_a_matching_name_is_kept_and_adapted(self):
        skill_dir = self.skill("ketchup", "ketchup")
        self.assertTrue(pstack_opencodex.adapt_skill(skill_dir, self.root))
        text = (skill_dir / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\nname: ketchup\n"))
        self.assertIn(f"read {self.root}/HARNESS.md", text)
        self.assertEqual((skill_dir / "agents" / "openai.yaml").read_text(), EXPLICIT_ONLY_POLICY)


class OverlayPatches(unittest.TestCase):
    def test_every_patch_applies_to_upstream_without_offset_or_fuzz(self):
        if shutil.which("patch") is None:
            self.skipTest("patch is not available")
        # GNU patch translates its diagnostics. The C locale keeps "offset" and "fuzz" in English,
        # and LANGUAGE is dropped so gettext cannot pick another catalog.
        env = {key: value for key, value in os.environ.items() if key != "LANGUAGE"}
        env["LC_ALL"] = "C"
        version = subprocess.run(["patch", "--version"], capture_output=True, text=True, env=env)
        if "GNU patch" not in version.stdout:
            self.skipTest("offset and fuzz reporting is checked with GNU patch")
        patches = sorted((ROOT / "overlay" / "patches").glob("*.patch"))
        self.assertTrue(patches)
        for patch in patches:
            with self.subTest(patch=patch.name), tempfile.TemporaryDirectory() as tmp:
                targets = re.findall(r"^\+\+\+ b/(\S+)", patch.read_text(), re.M)
                self.assertTrue(targets, f"{patch.name} names no target file")
                for rel in targets:
                    (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / "upstream" / rel, Path(tmp) / rel)
                result = subprocess.run(
                    ["patch", "-p1", "--batch", "--forward", "--dry-run", "-F", "0", "-d", tmp, "-i", str(patch)],
                    capture_output=True, text=True, timeout=30, env=env,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertNotRegex(output, r"(?i)\boffset\b|\bfuzz\b")


if __name__ == "__main__":
    unittest.main()
