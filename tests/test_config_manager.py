from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config_manager import AppPaths, ConfigManager, resolve_app_paths
from app.core.models import BackupJob, BackupMode


class ConfigManagerTests(unittest.TestCase):
    def test_resolve_app_paths_in_dev_mode(self) -> None:
        module_file = Path("C:/workspace/DualShelf/app/core/config_manager.py")
        paths = resolve_app_paths(frozen=False, module_file=module_file)
        self.assertEqual(paths.app_root, Path("C:/workspace/DualShelf/app").resolve())
        self.assertEqual(paths.data_root, Path("C:/workspace/DualShelf/app/data").resolve())

    def test_resolve_app_paths_in_frozen_mode(self) -> None:
        executable = Path("C:/Portable/Portable Backup Tool.exe")
        paths = resolve_app_paths(frozen=True, executable_path=executable)
        self.assertEqual(paths.app_root, Path("C:/Portable").resolve())
        self.assertEqual(paths.data_root, Path("C:/Portable/data").resolve())

    def test_save_and_load_jobs_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            manager = ConfigManager(
                AppPaths(
                    app_root=app_root,
                    data_root=app_root / "data",
                    jobs_file=app_root / "data" / "jobs.json",
                    default_log_root=app_root / "data" / "logs",
                    frozen=False,
                )
            )
            jobs = [
                BackupJob(
                    id="job-001",
                    name="Test Job",
                    sources=[str(app_root / "src")],
                    destination=str(app_root / "dest"),
                    mode=BackupMode.APPEND,
                )
            ]

            manager.save_jobs(jobs)
            loaded = manager.load_jobs()
            self.assertIsNone(loaded.error_message)
            self.assertEqual(len(loaded.jobs), 1)
            self.assertEqual(loaded.jobs[0].name, "Test Job")

    def test_load_jobs_returns_error_on_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            paths = AppPaths(
                app_root=app_root,
                data_root=app_root / "data",
                jobs_file=app_root / "data" / "jobs.json",
                default_log_root=app_root / "data" / "logs",
                frozen=False,
            )
            manager = ConfigManager(paths)
            manager.ensure_storage()
            paths.jobs_file.write_text("{ invalid json", encoding="utf-8")

            loaded = manager.load_jobs()
            self.assertEqual(loaded.jobs, [])
            self.assertIsNotNone(loaded.error_message)


if __name__ == "__main__":
    unittest.main()
