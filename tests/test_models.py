import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pstack_opencodex.py"
sys.path.insert(0, str(ROOT / "tools"))
from pstack_opencodex import parse_roles, upstream_roles  # noqa: E402

OPUS = "claude-opus-5-5-xhigh"
GROK = "grok-4.7-xhigh-fast"

# The role table in upstream setup-pstack step 5 at cursor/plugins 88d4751 (pstack 0.15.29),
# written out by hand so the tests do not take their expectations from the parser under test.
# Update it when a sync changes upstream's defaults; that change should be reviewed.
DEFAULTS_AT_0_15_29 = {
    "feature, refactoring": [GROK],
    "bug-fix": [GROK],
    "perf-issue": [GROK],
    "hillclimb": [GROK],
    "judgment and prose": [OPUS],
    "hardest tasks": [OPUS],
    "how explorer": [GROK],
    "how explainer": [OPUS],
    "why investigators": [GROK],
    "why synthesizer": [OPUS],
    "reflect tooling": [GROK],
    "reflect judgment, divergent, synthesizer": [OPUS],
    "arena runners": [OPUS, GROK],
    "arena cross-judge pool": [OPUS, GROK],
    "swarm workers": [GROK],
    "architect runners": [OPUS, GROK],
    "interrogate reviewers": [OPUS, GROK],
}
PANELS = {"arena runners", "arena cross-judge pool", "architect runners", "interrogate reviewers"}

# What each default must resolve to against the synthetic catalog below: the provider-prefixed
# slug and xhigh, with Grok's speed suffix dropped rather than carried into the model or effort.
RESOLVED = {
    OPUS: ("anthropic/claude-opus-5-5", "xhigh"),
    GROK: ("devin/grok-4.7", "xhigh"),
}

# One check-models line for a resolved value, e.g.
# "OK  arena runners: grok-4.7-xhigh-fast -> model=devin/grok-4.7 reasoning_effort=xhigh".
# Anything after the effort (a clamp note, "[not an upstream role line]") makes the line not match.
OK_LINE = re.compile(r"OK +(?P<label>[^:]+): (?P<value>\S+) -> model=(?P<slug>\S+) reasoning_effort=(?P<effort>\S+)")


def levels(*efforts):
    return [{"effort": effort} for effort in efforts]


# SYNTHETIC test catalog, not a real Codex catalog. It lists only the model families
# that pstack 0.15.29 (cursor/plugins 88d4751) names as role defaults in setup-pstack:
# claude-opus-5-5-xhigh and grok-4.7-xhigh-fast. Slugs follow the provider-prefixed
# form that HARNESS.md describes (anthropic/claude-*, devin/grok-*). Passing against it
# shows the names and efforts resolve; it does not show a live provider accepts them.
SYNTHETIC_CATALOG = {
    "synthetic": "test fixture for check-models --defaults; not a real Codex model catalog",
    "models": [
        {"slug": "anthropic/claude-opus-5-5", "supported_reasoning_levels": levels("low", "medium", "high", "xhigh", "max")},
        {"slug": "devin/grok-4.7", "supported_reasoning_levels": levels("low", "medium", "high", "xhigh")},
    ],
}


class UpstreamDefaultModels(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pstack-models-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def check_defaults(self, catalog):
        path = self.root / "synthetic-catalog.json"
        path.write_text(json.dumps(catalog))
        # CODEX_HOME points into the temporary directory so no real settings or cache can be read.
        env = {**os.environ, "CODEX_HOME": str(self.root)}
        return subprocess.run(
            [sys.executable, str(TOOL), "check-models", "--defaults", "--catalog", str(path)],
            env=env, capture_output=True, text=True, timeout=30,
        )

    def test_upstream_default_table_is_the_0_15_29_table(self):
        self.assertEqual(len(DEFAULTS_AT_0_15_29), 17)
        self.assertEqual({label for label, values in DEFAULTS_AT_0_15_29.items() if len(values) == 2}, PANELS)
        self.assertEqual(sum(len(values) for values in DEFAULTS_AT_0_15_29.values()), 21)
        self.assertEqual(upstream_roles(), DEFAULTS_AT_0_15_29)

    def test_upstream_default_models_resolve_against_the_synthetic_catalog(self):
        result = self.check_defaults(SYNTHETIC_CATALOG)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual([line for line in lines if line.startswith(("ERR", "--"))], [])
        ok_lines = [line for line in lines if line.startswith("OK")]
        rows = []
        for line in ok_lines:
            match = OK_LINE.fullmatch(line)
            self.assertIsNotNone(match, f"unexpected check-models line: {line!r}")
            rows.append((match["label"], match["value"], match["slug"], match["effort"]))
        expected = Counter(
            (label, value, *RESOLVED[value]) for label, values in DEFAULTS_AT_0_15_29.items() for value in values
        )
        self.assertEqual(len(rows), 21)
        self.assertEqual(Counter(rows), expected)
        for label, value, slug, effort in rows:
            with self.subTest(label=label, value=value):
                self.assertIn("/", slug, "the resolved model keeps its provider prefix")
                self.assertEqual(effort, "xhigh")
                self.assertNotIn("fast", slug)
                self.assertNotIn("fast", effort)
        for panel in sorted(PANELS):
            with self.subTest(panel=panel):
                slugs = sorted(slug for label, _, slug, _ in rows if label == panel)
                self.assertEqual(slugs, ["anthropic/claude-opus-5-5", "devin/grok-4.7"])

    def test_a_default_family_missing_from_the_catalog_fails(self):
        without_grok = {**SYNTHETIC_CATALOG, "models": [m for m in SYNTHETIC_CATALOG["models"] if "grok" not in m["slug"]]}
        result = self.check_defaults(without_grok)
        self.assertNotEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        grok_values = sum(values.count(GROK) for values in DEFAULTS_AT_0_15_29.values())
        missing = [line for line in lines if line.startswith("ERR") and line.endswith("grok-4.7 is not in the Codex catalog")]
        self.assertEqual(len(missing), grok_values)
        self.assertEqual(sum(line.startswith("OK") for line in lines), 21 - grok_values)

    def test_example_settings_cover_exactly_the_upstream_roles(self):
        example = parse_roles((ROOT / "overlay" / "pstack-models.example.md").read_text())
        self.assertEqual(set(example), set(DEFAULTS_AT_0_15_29))
        self.assertEqual(set(example), set(upstream_roles()))


if __name__ == "__main__":
    unittest.main()
