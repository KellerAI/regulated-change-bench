#!/usr/bin/env python3
"""Publication-gate regressions use synthetic names and token-shaped fixtures only."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANARY = "ZZCANARYONE"
FIXTURE = ROOT / "scripts" / "fixtures" / "gate-terms-canary.sha256"


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "tree"
        (self.root / "scripts").mkdir(parents=True)
        for name in ("gate.sh", "gate_terms.py"):
            shutil.copyfile(ROOT / "scripts" / name, self.root / "scripts" / name)
        self.rules = Path(self.tmp.name) / "private.sha256"
        shutil.copyfile(FIXTURE, self.rules)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def run_gate(self, rules=True):
        env = os.environ.copy()
        env.pop("GATE_TERMS_FILE", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHON"] = sys.executable
        if rules:
            env["GATE_TERMS_FILE"] = str(self.rules if rules is True else rules)
        return subprocess.run(["sh", "scripts/gate.sh"], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def assert_hit(self, result, path, term=CANARY):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertRegex(result.stdout, re.escape(path) + r":[0-9]+")
        self.assertNotIn(term, result.stdout + result.stderr)
        self.assertNotIn("checks passed", result.stdout)

    def test_clean_private_and_explicit_public_mode(self):
        private = self.run_gate()
        self.assertEqual(private.returncode, 0, private.stderr)
        public = self.run_gate(False)
        self.assertEqual(public.returncode, 0, public.stderr)
        self.assertIn("private name scan not configured", public.stdout)

    def test_original_public_rule_stores_removed(self):
        self.assertFalse((ROOT / "scripts" / "gate-terms.sha256").exists())
        self.assertIsNone(re.search(r"^TERMS=", (ROOT / "scripts" / "gate.sh").read_text(), re.M))

    def test_own_sources_and_same_named_files_are_scanned(self):
        for path in ("scripts/gate.sh", "scripts/gate_terms.py", "docs/gate.sh",
                     "docs/CODEOWNERS", "docs/gate-terms.sha256"):
            with self.subTest(path=path):
                target = self.root / path
                original = target.read_text() if target.exists() else None
                self.write(path, (original or "") + "\n# " + CANARY + "\n")
                self.assert_hit(self.run_gate(), path)
                if original is None:
                    target.unlink()
                else:
                    target.write_text(original)

    def test_normalization_and_whole_token_boundaries(self):
        for path, text in (("one.txt", CANARY.lower()), ("two.txt", "zz   CANARYTWO"),
                           ("three.txt", "ZZ planted--Canary"),
                           ("unicode.txt", "ＺＺＣＡＮＡＲＹＯＮＥ")):
            self.write(path, text)
        self.write("clean.txt", "zzplantedcanary\nzz planted\nxxzz planted canary")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()),
                         {"one.txt:1", "two.txt:1", "three.txt:1", "unicode.txt:1"})

    def test_public_url_does_not_exempt_the_rest_of_a_line(self):
        self.write("docs/example.md", "https://kellerai.io/resources/benchmarking-regulated-change-review " + CANARY)
        self.assert_hit(self.run_gate(), "docs/example.md")

    def test_only_ownership_handles_have_a_name_exception(self):
        self.write(".github/CODEOWNERS", "* @" + CANARY + "-example\n")
        self.assertEqual(self.run_gate().returncode, 0)
        self.write(".github/CODEOWNERS", "* @" + CANARY + "-example # " + CANARY)
        self.assert_hit(self.run_gate(), ".github/CODEOWNERS")

    def test_path_and_credential_hits_are_redacted_without_private_config(self):
        examples = (("path.txt", "/" + "Users" + "/fixture"),
                    ("token.txt", "AKIA" + "X" * 16),
                    ("nested/bedrock.py", "ASIA" + "X" * 16))
        for path, value in examples:
            self.write(path, value)
            self.assert_hit(self.run_gate(False), path, value)
            (self.root / path).unlink()

    def test_nul_does_not_hide_a_name(self):
        (self.root / "mixed.bin").write_bytes(b"\0" + CANARY.encode())
        self.assert_hit(self.run_gate(), "mixed.bin")

    def test_test_cache_paths_do_not_hide_published_content(self):
        self.write(".pytest_cache/exposure.txt", CANARY)
        self.assert_hit(self.run_gate(), ".pytest_cache/exposure.txt")

    def test_missing_empty_malformed_and_in_tree_rules_fail(self):
        self.rules.unlink()
        self.assertEqual(self.run_gate().returncode, 2)
        for value in ("", "not-a-digest", "ff\n"):
            self.rules.write_text(value)
            self.assertEqual(self.run_gate().returncode, 2)
        self.write("rules.sha256", FIXTURE.read_text())
        self.assertEqual(self.run_gate(self.root / "rules.sha256").returncode, 2)
        self.rules.unlink()
        self.rules.symlink_to(self.root / "rules.sha256")
        self.assertEqual(self.run_gate().returncode, 2)

    def test_file_and_directory_symlinks_fail_closed(self):
        outside = Path(self.tmp.name) / "outside"
        outside.write_text(CANARY)
        (self.root / "link").symlink_to(outside)
        result = self.run_gate()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(CANARY, result.stdout + result.stderr)
        (self.root / "link").unlink()
        (self.root / "dirlink").symlink_to(Path(self.tmp.name), target_is_directory=True)
        self.assertEqual(self.run_gate().returncode, 2)


if __name__ == "__main__":
    unittest.main()
