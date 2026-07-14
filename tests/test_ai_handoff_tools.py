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
        shutil.copy2(ROOT / "runtime_config.py", root / "runtime_config.py")
        shutil.copy2(ROOT / "core.py", root / "core.py")
        shutil.copytree(ROOT / "economy", root / "economy", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "cogs", root / "cogs", ignore=shutil.ignore_patterns("__pycache__"))
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
        state["productionStatus"]["value"]["enabled"] = True
        self._write_state(root, state)
        self.assertIn("production ditandai aktif tanpa approval eksplisit", verify_ai_handoff.verify(root))
        state = json.loads(json.dumps(self.state))
        next(row for row in state["phaseStatuses"]["value"] if row["id"] == "phase5")["status"] = "implemented"
        self._write_state(root, state)
        self.assertIn("Phase 5 tidak berada pada guard status", verify_ai_handoff.verify(root))

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


if __name__ == "__main__":
    unittest.main()
