"""Tests for the non-mutating Living PRD tooling."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_ai_handoff
import update_ai_handoff
import verify_ai_handoff


class LivingPrdToolingTests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads((ROOT / "docs" / "project_state.json").read_text(encoding="utf-8"))

    def _fixture_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "docs").mkdir()
        shutil.copy2(ROOT / "docs" / "project_state.json", root / "docs" / "project_state.json")
        shutil.copy2(ROOT / "docs" / "AI_CODER_HANDOFF.md", root / "docs" / "AI_CODER_HANDOFF.md")
        shutil.copy2(ROOT / "docs" / "PHASE5_CASINO_PRD.md", root / "docs" / "PHASE5_CASINO_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE6_CRYPTO_PRD.md", root / "docs" / "PHASE6_CRYPTO_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE7_MINING_PRD.md", root / "docs" / "PHASE7_MINING_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE8_GIVEAWAY_OPTIONS_PRD.md", root / "docs" / "PHASE8_GIVEAWAY_OPTIONS_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE9A_BACKEND_SAFETY_PRD.md", root / "docs" / "PHASE9A_BACKEND_SAFETY_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE9B_DASHBOARD_NOTIFICATION_ROUTING_PRD.md", root / "docs" / "PHASE9B_DASHBOARD_NOTIFICATION_ROUTING_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE9C_FINAL_QA_PRODUCTION_READINESS_PRD.md", root / "docs" / "PHASE9C_FINAL_QA_PRODUCTION_READINESS_PRD.md")
        shutil.copy2(ROOT / "docs" / "PHASE9C_STAGING_EVIDENCE_SCHEMA.json", root / "docs" / "PHASE9C_STAGING_EVIDENCE_SCHEMA.json")
        shutil.copy2(ROOT / "runtime_config.py", root / "runtime_config.py")
        shutil.copy2(ROOT / "core.py", root / "core.py")
        shutil.copytree(ROOT / "economy", root / "economy", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "cogs", root / "cogs", ignore=shutil.ignore_patterns("__pycache__"))
        (root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "migrate_economy_phase5.py", root / "scripts" / "migrate_economy_phase5.py")
        shutil.copy2(ROOT / "scripts" / "migrate_economy_phase6.py", root / "scripts" / "migrate_economy_phase6.py")
        shutil.copy2(ROOT / "scripts" / "migrate_economy_phase7.py", root / "scripts" / "migrate_economy_phase7.py")
        shutil.copy2(ROOT / "scripts" / "migrate_economy_phase8.py", root / "scripts" / "migrate_economy_phase8.py")
        shutil.copy2(ROOT / "scripts" / "migrate_phase9a_backend_safety.py", root / "scripts" / "migrate_phase9a_backend_safety.py")
        shutil.copy2(ROOT / "scripts" / "migrate_phase9b_dashboard.py", root / "scripts" / "migrate_phase9b_dashboard.py")
        for name in (
            "simulate_phase9c_full_system.py", "reconcile_phase9c_full_system.py",
            "run_phase9c_local_qa.py", "run_phase9c_staging.py",
            "verify_phase9c_staging_evidence.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
        (root / "dashboard-example").mkdir()
        shutil.copy2(ROOT / "dashboard-example" / "middleware.ts", root / "dashboard-example" / "middleware.ts")
        (root / "dashboard-example" / "app" / "economy").mkdir(parents=True)
        shutil.copy2(ROOT / "dashboard-example" / "app" / "economy" / "page.tsx",
                     root / "dashboard-example" / "app" / "economy" / "page.tsx")
        return root

    @staticmethod
    def _write_state(root: Path, state: dict) -> None:
        (root / "docs" / "project_state.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        (root / "docs" / "AI_CODER_HANDOFF.md").write_bytes(generate_ai_handoff.render_handoff(state))

    def test_render_is_deterministic_utf8_lf_with_one_final_newline(self):
        first = generate_ai_handoff.render_handoff(self.state)
        second = generate_ai_handoff.render_handoff(self.state)
        self.assertEqual(first, second)
        self.assertNotIn(b"\r\n", first)
        self.assertTrue(first.endswith(b"\n"))
        self.assertFalse(first.endswith(b"\n\n"))
        self.assertTrue(first.startswith(
            b"THIS FILE IS GENERATED.\nDO NOT EDIT IT MANUALLY.\n"
            b"Update docs/project_state.json and run:\npython scripts/update_ai_handoff.py\n"
        ))
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
        self.assertIn(b"## Phase 5 Casino\n", first)
        self.assertIn(b"## Phase 6 Crypto\n", first)
        self.assertIn(b"## Phase 7 Mining\n", first)
        self.assertIn(b"## Phase 8 Giveaway And Eternal Options\n", first)
        self.assertIn(b"## Phase 9A Backend Safety Foundation\n", first)
        self.assertIn(b"## Phase 9B Economy Dashboard And Notification Routing\n", first)
        self.assertIn(b"## Phase 9C Final QA And Production Readiness\n", first)

    def test_phase7_profile_claim_simulation_and_production_guards(self):
        mutations = (
            ("productionEnabled", True, "Phase 7 production guard tidak valid"),
            ("productionMigrated", True, "Phase 7 production guard tidak valid"),
            ("status", "planning", "Phase 7 status harus implemented_staging_ready"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase7Mining"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(expected, verify_ai_handoff.verify(root))
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase7Mining"]["value"]["accounting"]["claimUsesEconomyTransaction"] = True
        self._write_state(root, state)
        self.assertIn("Phase 7 asset-only claim contract tidak valid", verify_ai_handoff.verify(root))

    def test_phase6_runtime_migration_simulation_and_production_guards(self):
        mutations = (
            ("productionEnabled", True, "Phase 6 production guard tidak valid"),
            ("productionMigrated", True, "Phase 6 production guard tidak valid"),
            ("productionSeeded", True, "Phase 6 production guard tidak valid"),
            ("status", "planning", "Phase 6 status harus implemented_staging_ready"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase6Crypto"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(expected, verify_ai_handoff.verify(root))
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase6Crypto"]["value"]["simulation"]["artifactSha256"] = "0" * 64
        state["phase6Crypto"]["value"]["simulation"]["passed"] = False
        self._write_state(root, state)
        self.assertIn("Phase 6 simulation result tidak valid", verify_ai_handoff.verify(root))

    def test_generator_import_has_no_file_side_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = (
                "import pathlib,sys; p=pathlib.Path(sys.argv[1]); before=sorted(x.name for x in p.iterdir()); "
                "sys.path.insert(0,sys.argv[2]); import generate_ai_handoff; "
                "after=sorted(x.name for x in p.iterdir()); assert before == after"
            )
            result = subprocess.run(
                [sys.executable, "-c", script, temporary, str(SCRIPTS)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_repository_state_passes_static_verification(self):
        self.assertEqual(verify_ai_handoff.verify(ROOT), [])

    def test_stale_markdown_invalid_json_and_schema_fail(self):
        root = self._fixture_root()
        handoff = root / "docs" / "AI_CODER_HANDOFF.md"
        handoff.write_bytes(handoff.read_bytes() + b"manual edit\n")
        self.assertIn("AI_CODER_HANDOFF.md stale atau diedit manual", verify_ai_handoff.verify(root))
        (root / "docs" / "project_state.json").write_text("{bad", encoding="utf-8")
        self.assertTrue(any("project_state.json tidak valid" in issue for issue in verify_ai_handoff.verify(root)))
        self._write_state(root, {**self.state, "schemaVersion": 2})
        self.assertIn("schemaVersion tidak didukung", verify_ai_handoff.verify(root))

    def test_required_nested_fields_and_commit_references_fail_closed(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        del state["project"]["value"]["repositoryPath"]
        self._write_state(root, state)
        self.assertIn("nested field wajib hilang: project", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        state["latestCompletedTask"]["value"]["commit"] = "not-a-hash"
        self._write_state(root, state)
        self.assertIn("commit reference invalid", verify_ai_handoff.verify(root))

    def test_verifier_does_not_rewrite_fixture_files(self):
        root = self._fixture_root()
        before_state = (root / "docs" / "project_state.json").read_bytes()
        before_handoff = (root / "docs" / "AI_CODER_HANDOFF.md").read_bytes()
        self.assertEqual(verify_ai_handoff.verify(root), [])
        self.assertEqual((root / "docs" / "project_state.json").read_bytes(), before_state)
        self.assertEqual((root / "docs" / "AI_CODER_HANDOFF.md").read_bytes(), before_handoff)

    def test_duplicate_and_checksum_validation(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["migrations"]["value"].append(dict(state["migrations"]["value"][3]))
        self._write_state(root, state)
        self.assertIn("migration versions duplikat", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        state["migrations"]["value"][3]["checksum"] = "0" * 64
        self._write_state(root, state)
        self.assertIn("checksum migrasi 301 tidak cocok source", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        state["catalogs"]["value"][0]["checksum"] = "f" * 64
        self._write_state(root, state)
        self.assertIn("catalog checksum tidak cocok source", verify_ai_handoff.verify(root))

    def test_flags_ownership_alias_and_mismatch_guards(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["featureFlags"]["value"]["ECONOMY_PHASE4_ENABLED"] = True
        self._write_state(root, state)
        self.assertIn("feature flag documentation tidak cocok runtime_config.py", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        state["commandOwnership"]["value"]["/rank"] = "RPG"
        self._write_state(root, state)
        self.assertIn("ownership /rank tidak cocok dengan source", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        state["documentedMismatches"]["value"] = []
        self._write_state(root, state)
        self.assertIn("documented mismatch /rank tidak valid", verify_ai_handoff.verify(root))
        (root / "cogs" / "bad_alias.py").write_text(
            'register_prefix_command_handler("vouch", handler)\n', encoding="utf-8"
        )
        self.assertTrue(any("forbidden aliases" in issue for issue in verify_ai_handoff.verify(root)))

    def test_secret_production_and_phase5_guards(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["project"]["value"]["leak"] = "discord_token=" + ("a" * 16)
        self._write_state(root, state)
        self.assertTrue(any("kemungkinan secret" in issue for issue in verify_ai_handoff.verify(root)))
        state = json.loads(json.dumps(self.state))
        state["project"]["value"]["paymentAccount"] = "sensitive-placeholder"
        self._write_state(root, state)
        self.assertTrue(any("private environment/data" in issue for issue in verify_ai_handoff.verify(root)))
        state = json.loads(json.dumps(self.state))
        state["productionStatus"]["value"]["enabled"] = True
        self._write_state(root, state)
        self.assertIn("production ditandai aktif tanpa approval eksplisit", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        next(row for row in state["phaseStatuses"]["value"] if row["id"] == "phase5")["status"] = "implemented"
        self._write_state(root, state)
        self.assertIn("Phase 5 tidak berada pada guard status", verify_ai_handoff.verify(root))

    def test_phase5_implementation_and_production_guards(self):
        mutations = (
            ("implementationStatus", "not_started"),
            ("productionStatus", "approved"),
            ("productionMigrated", True),
            ("productionEnabled", True),
            ("runtimeFeatureFlagExists", False),
            ("migrationExists", False),
            ("planningDocument", "docs/missing.md"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase5Casino"]["value"][field] = value
                self._write_state(root, state)
                self.assertTrue(any("Phase 5 planning" in issue for issue in verify_ai_handoff.verify(root)))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["pendingWork"]["value"] = ["Connected Discord staging validation"]
        self._write_state(root, state)
        self.assertIn("Phase 5 follow-up tidak tercatat sebagai pending work", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        runtime = root / "runtime_config.py"
        runtime.write_text(runtime.read_text(encoding="utf-8").replace(
            'ECONOMY_PHASE5_ENABLED = _env_bool("ECONOMY_PHASE5_ENABLED", False)',
            'REMOVED_PHASE5_FLAG = False',
        ), encoding="utf-8")
        constants = root / "economy" / "constants.py"
        constants.write_text(constants.read_text(encoding="utf-8").replace(
            "ECONOMY_PHASE5_ENABLED", "REMOVED_PHASE5_FLAG"
        ), encoding="utf-8")
        self.assertIn("Phase 5 runtime flag existence tidak cocok state", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        (root / "scripts" / "migrate_economy_phase5.py").unlink()
        self.assertIn("Phase 5 migration/runtime module existence tidak cocok state", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["simulationResult"]["passed"] = False
        state["phase5Casino"]["value"]["simulationResult"]["stagingReady"] = False
        state["phase5Casino"]["value"]["simulationResult"]["blockingDecision"] = "D02"
        self._write_state(root, state)
        self.assertIn("Phase 5 D18/D02 implementation result tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["simulationResult"]["blackjack"]["simulatedRtp"] = 0.99
        self._write_state(root, state)
        self.assertIn("Phase 5 D18/D02 implementation result tidak valid", verify_ai_handoff.verify(root))

    def test_phase5_decision_ids_statuses_and_d02_gate(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["ownerDecisionRecords"].pop()
        self._write_state(root, state)
        self.assertIn("Phase 5 decision records harus tepat D01-D20 dan unik", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        decisions = state["phase5Casino"]["value"]["ownerDecisionRecords"]
        decisions[-1]["id"] = "D01"
        self._write_state(root, state)
        self.assertIn("Phase 5 decision records harus tepat D01-D20 dan unik", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["ownerDecisionRecords"][0]["status"] = "approved"
        self._write_state(root, state)
        self.assertIn("Phase 5 decision approval status tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        d02 = next(row for row in state["phase5Casino"]["value"]["ownerDecisionRecords"] if row["id"] == "D02")
        d02["status"] = "provisionally_approved"
        self._write_state(root, state)
        self.assertIn("Phase 5 D18/D02 implementation result tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        d02 = next(row for row in state["phase5Casino"]["value"]["ownerDecisionRecords"] if row["id"] == "D02")
        d02["condition"] = ""
        state["phase5Casino"]["value"]["simulationAcceptanceGates"] = []
        self._write_state(root, state)
        issues = verify_ai_handoff.verify(root)
        self.assertIn("Phase 5 D02 simulation/reapproval gate tidak valid", issues)
        self.assertIn("Phase 5 D02 structured simulation gate tidak valid", issues)

    def test_phase5_resolved_decisions_and_approved_values(self):
        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["ownerDecisionStatus"] = "approved"
        self._write_state(root, state)
        self.assertIn("Phase 5 owner decision status tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase5Casino"]["value"]["unresolvedOwnerDecisions"] = ["stale"]
        self._write_state(root, state)
        self.assertIn("Phase 5 masih memiliki unresolved owner decisions", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["blockers"]["value"].append("Phase 5 owner decisions must be approved before implementation.")
        self._write_state(root, state)
        self.assertIn("Phase 5 stale owner-decision blocker masih ada", verify_ai_handoff.verify(root))

        for field, value, message in (
            ("wagerIncrementEcy", 500, "Phase 5 wager increment harus 1000 ECY"),
            ("fixedPricesEcy", {"gacha": 500, "lootBox": 1000}, "Phase 5 fixed Casino prices harus 1000 ECY"),
            ("authorizationClasses", {}, "Phase 5 Casino authorization classes tidak valid"),
            ("approvedMigration", {"version": 501, "name": "bad"}, "Phase 5 approved migration identity tidak valid"),
            ("approvedFutureFeatureFlagName", "BAD_FLAG", "Phase 5 approved feature flag identity tidak valid"),
        ):
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase5Casino"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(message, verify_ai_handoff.verify(root))

        for field, message in (
            ("migrationExists", "Phase 5 migration existence guard tidak valid"),
            ("runtimeFeatureFlagExists", "Phase 5 runtime feature flag existence guard tidak valid"),
        ):
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase5Casino"]["value"][field] = False
                self._write_state(root, state)
                self.assertIn(message, verify_ai_handoff.verify(root))

    def test_verifier_source_is_static_and_update_propagates_failure(self):
        source = (SCRIPTS / "verify_ai_handoff.py").read_text(encoding="utf-8")
        self.assertNotIn("import main", source)
        self.assertNotIn("import core", source)
        self.assertNotIn("from economy", source)
        self.assertNotIn("import economy", source)
        self.assertNotIn("sqlite3.connect", source)
        with mock.patch.object(update_ai_handoff, "_run", side_effect=[7]) as run:
            self.assertEqual(update_ai_handoff.main(), 7)
            run.assert_called_once_with("generate_ai_handoff.py")
        with mock.patch.object(update_ai_handoff, "_run", side_effect=[0, 9]) as run:
            self.assertEqual(update_ai_handoff.main(), 9)
            self.assertEqual(run.call_count, 2)

    def test_phase9a_security_state_and_migration_guards(self):
        mutations = (
            ("status", "planning", "Phase 9A status harus implemented_local_verification"),
            ("implementationStatus", "not_started", "Phase 9A implementation status tidak valid"),
            ("productionMigrated", True, "Phase 9A production guard tidak valid"),
            ("productionEnabled", True, "Phase 9A production guard tidak valid"),
            ("featureFlagAdded", True, "Phase 9A tidak boleh memiliki Economy feature flag"),
            ("connectedDiscordOauthStaging", "passed", "Phase 9A connected OAuth staging harus pending"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase9aBackendSafety"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(expected, verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9aBackendSafety"]["value"]["migration"]["version"] = 901
        self._write_state(root, state)
        self.assertIn("Phase 9A migration identity tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9aBackendSafety"]["value"]["publicSurface"]["otherPublicDataRoutes"] = 1
        self._write_state(root, state)
        self.assertIn("Phase 9A public surface tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9aBackendSafety"]["value"]["permissionClasses"].pop()
        self._write_state(root, state)
        self.assertIn("Phase 9A permission classes tidak valid", verify_ai_handoff.verify(root))

    def test_phase9b_delivery_migration_and_production_guards(self):
        mutations = (
            ("status", "planning", "Phase 9B status harus implemented_local_verification"),
            ("implementationStatus", "not_started", "Phase 9B implementation status tidak valid"),
            ("productionMigrated", True, "Phase 9B production guard tidak valid"),
            ("productionEnabled", True, "Phase 9B production guard tidak valid"),
            ("featureFlagAdded", True, "Phase 9B tidak boleh memiliki feature flag"),
            ("connectedDiscordOauthStaging", "passed", "Phase 9B connected staging harus pending"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase9bDashboardNotificationRouting"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(expected, verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9bDashboardNotificationRouting"]["value"]["migration"]["version"] = 911
        self._write_state(root, state)
        self.assertIn("Phase 9B migration identity tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9bDashboardNotificationRouting"]["value"]["delivery"]["automaticReviewRetry"] = True
        self._write_state(root, state)
        self.assertIn("Phase 9B durable delivery contract tidak valid", verify_ai_handoff.verify(root))

    def test_phase9c_baseline_simulation_staging_and_production_guards(self):
        cases = (
            ("status", "planning", "Phase 9C status harus ready_for_connected_staging"),
            ("implementationStatus", "not_started", "Phase 9C implementation status tidak valid"),
            ("migrationAdded", True, "Phase 9C tidak boleh menambah migrasi atau feature flag"),
            ("featureFlagAdded", True, "Phase 9C tidak boleh menambah migrasi atau feature flag"),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                root = self._fixture_root()
                state = json.loads(json.dumps(self.state))
                state["phase9cFinalQa"]["value"][field] = value
                self._write_state(root, state)
                self.assertIn(expected, verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9cFinalQa"]["value"]["simulation"]["users"] = 999
        self._write_state(root, state)
        self.assertIn("Phase 9C simulation contract tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9cFinalQa"]["value"]["connectedStaging"]["networkAttempted"] = True
        self._write_state(root, state)
        self.assertIn("Phase 9C connected staging guard tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9cFinalQa"]["value"]["connectedStaging"]["credentialEnvironment"][1] = "DISCORD_CLIENT_ID"
        self._write_state(root, state)
        self.assertIn("Phase 9C staging credential contract tidak valid", verify_ai_handoff.verify(root))

        root = self._fixture_root()
        state = json.loads(json.dumps(self.state))
        state["phase9cFinalQa"]["value"]["production"]["accessed"] = True
        self._write_state(root, state)
        self.assertIn("Phase 9C production guard tidak valid", verify_ai_handoff.verify(root))


if __name__ == "__main__":
    unittest.main()
