import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from all_seeing_eye import paths
from all_seeing_eye.daily_hub import runner


class PathConfigurationTests(unittest.TestCase):
    def test_explicit_directory_overrides_discovery_and_expands_home(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Sibling").mkdir()
            legacy = root / "Legacy"
            legacy.mkdir()
            with patch.object(paths, "ROOT", root / "Model_4"), \
                    patch.dict(os.environ, {"MODEL4_TEST_DIR": "~/Custom Models"}):
                result = paths.project_path("MODEL4_TEST_DIR", "Sibling", legacy)
            self.assertEqual(result, (Path.home() / "Custom Models").resolve())

    def test_sibling_then_legacy_then_missing_sibling(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sibling = root / "Sibling"
            legacy = root / "Legacy"
            with patch.object(paths, "ROOT", root / "Model_4"), \
                    patch.dict(os.environ, {"MODEL4_TEST_DIR": ""}):
                self.assertEqual(paths.project_path("MODEL4_TEST_DIR", "Sibling", legacy), sibling)
                legacy.mkdir()
                self.assertEqual(paths.project_path("MODEL4_TEST_DIR", "Sibling", legacy), legacy)
                sibling.mkdir()
                self.assertEqual(paths.project_path("MODEL4_TEST_DIR", "Sibling", legacy), sibling)

    def test_worker_keeps_app_interpreter_when_upstream_python_differs(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(runner, "HUB", Path(folder)), \
                patch.object(runner, "PYTHON", Path("/external/python")), \
                patch.object(runner.subprocess, "Popen") as start:
            runner.start_run("2026-09-01", "saved")
        self.assertEqual(start.call_args.args[0][0], sys.executable)

    def test_missing_upstream_script_explains_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            instance = runner.Runner.__new__(runner.Runner)
            with self.assertRaisesRegex(FileNotFoundError, "MODEL4_GBM_DIR"):
                instance.command(Path(folder), "missing.py")
