#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallSmokeTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="jcode-install-home-"))
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        self.result = subprocess.run(
            [str(ROOT / "tests" / "smoke_install.sh")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_script_succeeds(self):
        self.assertEqual(
            self.result.returncode,
            0,
            self.result.stdout + self.result.stderr,
        )

    def test_installed_structure(self):
        jcode = self.home / ".jcode"
        for name in ("prompt-overlay.md", "swarm-prompt.md", "ARCHITECTURE.md", "roles"):
            link = jcode / name
            self.assertTrue(link.is_symlink(), name)
            self.assertTrue(link.resolve(strict=True).exists(), name)
        skills = jcode / "skills"
        self.assertTrue(skills.is_dir())
        self.assertTrue(any(skills.iterdir()))
        agents = jcode / "AGENTS.md"
        self.assertTrue(agents.is_symlink())
        self.assertTrue(agents.resolve(strict=True).exists())


if __name__ == "__main__":
    unittest.main()
