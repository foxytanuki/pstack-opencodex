import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pstack_runtime import diagnose, model_route


def models(parent_surface="v1", child_surface="v1"):
    return {
        "gpt-6.1-sol": {"slug": "gpt-6.1-sol", "use_responses_lite": True, "multi_agent_version": parent_surface, "supported_reasoning_levels": [{"effort": "max"}]},
        "anthropic/claude-opus-5-5": {"slug": "anthropic/claude-opus-5-5", "multi_agent_version": child_surface, "supported_reasoning_levels": [{"effort": "max"}]},
    }


class RuntimeRules(unittest.TestCase):
    def report(self, surface, records=None, config=None, codex=None):
        return diagnose("gpt-6.1-sol", {"anthropic/claude-opus-5-5": ["how explainer"]}, records or models(), codex or {}, config or {"multiAgentMode": "v1"}, surface)

    def codes(self, report):
        return {issue["code"] for issue in report["issues"]}

    def test_unknown_session_never_inherits_v1_from_disk(self):
        report = self.report("unknown")
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertIn("session_surface_unknown", self.codes(report))

    def test_observed_v1_has_no_known_transport_block_but_is_not_live_proof(self):
        report = self.report("v1")
        self.assertEqual(report["status"], "CONFIGURATION_OK")
        self.assertFalse(report["live_delegation_verified"])

    def test_observed_v2_blocks_native_to_routed_even_with_v1_disk_pins(self):
        report = self.report("v2")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue({"session_catalog_mismatch", "encrypted_v2_task"} <= self.codes(report))

    def test_v1_leaf_child_does_not_make_native_v2_transport_readable(self):
        report = self.report("v2", models(parent_surface="v2"))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("encrypted_v2_task", self.codes(report))

    def test_disabled_child_is_blocked_on_an_observed_v1_session(self):
        report = self.report("v1", models(child_surface="disabled"))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("child_disabled", self.codes(report))

    def test_disabled_parent_cannot_delegate(self):
        report = self.report("v1", models(parent_surface="disabled"))
        self.assertIn("parent_disabled", self.codes(report))

    def test_each_experimental_mitigation_requires_live_confirmation(self):
        for config in ({"plaintextV2AgentMessages": True}, {"agentTaskRecovery": {"enabled": True}}):
            with self.subTest(config=config):
                report = self.report("v2", models(parent_surface="v2"), config)
                self.assertEqual(report["status"], "INCONCLUSIVE")
                self.assertIn("experimental_v2_mitigation", self.codes(report))
                self.assertFalse(report["live_delegation_verified"])

    def test_routed_parent_does_not_have_native_ciphertext_constraint(self):
        records = models(parent_surface="v2")
        records["gpt-6.1-sol"]["use_responses_lite"] = False
        records["gpt-6.1-sol"]["opencodex_catalog_kind"] = "combo-native-alias-v1"
        report = self.report("v2", records)
        self.assertEqual(report["status"], "CONFIGURATION_OK")

    def test_unknown_parent_route_is_inconclusive(self):
        records = models(parent_surface="v2")
        del records["gpt-6.1-sol"]["use_responses_lite"]
        report = self.report("v2", records)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertIn("route_unknown", self.codes(report))

    def test_native_forward_metadata_precedes_provider_namespace(self):
        self.assertEqual(model_route({"slug": "openai-codex/gpt-6.1-sol", "use_responses_lite": True}), "native")
        self.assertEqual(model_route({"slug": "openai-codex/unknown"}), "unknown")

    def test_global_override_conflicts_with_hybrid_native_v1(self):
        for flag in (True, {"enabled": True}, {"max_concurrent_threads_per_session": 4}):
            with self.subTest(flag=flag):
                report = self.report("v1", config={"multiAgentMode": "v2", "keepNativeChatGptOnV1": True}, codex={"features": {"multi_agent_v2": flag}})
                self.assertEqual(report["status"], "INCONCLUSIVE")
                self.assertIn("global_v2_override", self.codes(report))


class RuntimeCLI(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pstack-runtime-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "selected.json"
        self.roles = self.root / "models.md"
        self.codex = self.root / "config.toml"
        self.opencodex = self.root / "config.json"
        self.write_catalog(models())
        self.roles.write_text("how explainer: anthropic/claude-opus-5-5-max\n")
        self.codex.write_text(f"model_catalog_json = {json.dumps(str(self.catalog))}\n")
        self.opencodex.write_text(json.dumps({"multiAgentMode": "v1", "providers": {"secret": "DO_NOT_PRINT_ME"}}))

    def write_catalog(self, records):
        self.catalog.write_text(json.dumps({"models": list(records.values())}))

    def run_cli(self, *extra):
        return subprocess.run([sys.executable, str(ROOT / "tools/pstack_opencodex.py"), "check-runtime", "--parent-model", "gpt-6.1-sol", "--file", str(self.roles), "--codex-config", str(self.codex), "--opencodex-config", str(self.opencodex), "--json", *extra], text=True, capture_output=True, timeout=10)

    def test_default_cli_reads_authoritative_catalog_and_leaves_settings_intact(self):
        files = [self.catalog, self.roles, self.codex, self.opencodex]
        before = {path: path.read_bytes() for path in files}
        result = self.run_cli()
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["paths"]["catalog"], str(self.catalog))
        self.assertNotIn("DO_NOT_PRINT_ME", result.stdout + result.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in files})

    def test_exit_codes_for_observed_v1_and_v2(self):
        for surface, expected in (("v1", 0), ("v2", 1)):
            with self.subTest(surface=surface):
                result = self.run_cli("--session-surface", surface)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertFalse(json.loads(result.stdout)["live_delegation_verified"])

    def test_disabled_child_fails_name_check_and_runtime_check(self):
        self.write_catalog(models(child_surface="disabled"))
        result = self.run_cli("--session-surface", "v1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("child_disabled", result.stdout)
        names = subprocess.run([sys.executable, str(ROOT / "tools/pstack_opencodex.py"), "check-models", "--file", str(self.roles), "--catalog", str(self.catalog)], text=True, capture_output=True, timeout=10)
        self.assertEqual(names.returncode, 1)
        self.assertIn("disabled for collaboration", names.stdout)

    def test_profile_overrides_catalog_and_features(self):
        alternate = self.root / "profile.json"
        alternate.write_text(json.dumps({"models": list(models(child_surface="disabled").values())}))
        self.codex.write_text(f"model_catalog_json = {json.dumps(str(self.catalog))}\n[profiles.work]\nmodel_catalog_json = {json.dumps(str(alternate))}\n[profiles.work.features]\nmulti_agent_v2 = true\n")
        result = self.run_cli("--profile", "work", "--session-surface", "v1")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["paths"]["catalog"], str(alternate))
        self.assertTrue(report["configured"]["global_v2"])

    def test_explicit_catalog_override_wins_over_config(self):
        alternate = self.root / "override.json"
        alternate.write_text(json.dumps({"models": list(models(child_surface="disabled").values())}))
        result = self.run_cli("--catalog", str(alternate), "--session-surface", "v1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["paths"]["catalog"], str(alternate))

    def test_selected_native_role_is_not_blocked_by_unused_routed_roles(self):
        self.roles.write_text("how explainer: anthropic/claude-opus-5-5-max\nswarm workers: inherit-parent\n")
        self.write_catalog(models(parent_surface="v2", child_surface="disabled"))
        result = self.run_cli("--role", "swarm workers", "--session-surface", "v2")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual([child["model"] for child in report["children"]], ["gpt-6.1-sol"])

    def test_unknown_role_or_profile_returns_a_failed_diagnostic(self):
        for option in ("--role", "--profile"):
            with self.subTest(option=option):
                result = self.run_cli(option, "missing")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "invalid_input")

    def test_inherited_role_resolves_to_actual_parent(self):
        self.roles.write_text("how explainer: inherit-parent\n")
        self.write_catalog(models(parent_surface="v2"))
        result = self.run_cli("--session-surface", "v2")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["children"][0]["model"], "gpt-6.1-sol")

    def test_bad_input_fails_with_json_instead_of_traceback(self):
        bad_efforts = models()
        bad_efforts["gpt-6.1-sol"]["supported_reasoning_levels"] = [{}]
        for contents in ("not-json", "[]", '{"models": [null]}', json.dumps({"models": list(bad_efforts.values())})):
            with self.subTest(contents=contents):
                self.catalog.write_text(contents)
                result = self.run_cli()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "invalid_input")
                self.assertNotIn("Traceback", result.stderr)

    def test_missing_config_cannot_be_a_positive_result(self):
        self.opencodex.unlink()
        result = self.run_cli("--session-surface", "v1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("config_missing", result.stdout)

    def test_relative_configured_catalog_is_rejected_without_guessing(self):
        self.codex.write_text('model_catalog_json = "relative.json"\n')
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("catalog path must be absolute", result.stdout)


if __name__ == "__main__":
    unittest.main()
