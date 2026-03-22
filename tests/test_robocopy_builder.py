from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.models import BackupJob, BackupMode
from app.core.robocopy_builder import (
    RoboCopyBuilder,
    detect_duplicate_source_basenames,
    normalize_extension_patterns,
)


class RoboCopyBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = RoboCopyBuilder()

    def test_detect_duplicate_source_basenames(self) -> None:
        duplicates = detect_duplicate_source_basenames(
            [
                r"D:\Archive\PSP",
                r"E:\Other\PSP",
                r"D:\Archive\Music",
            ]
        )
        self.assertEqual(duplicates, ["psp"])

    def test_normalize_extension_patterns(self) -> None:
        normalized = normalize_extension_patterns([".tmp", "bak", "*.cache"])
        self.assertEqual(normalized, ["*.tmp", "*.bak", "*.cache"])

    def test_snapshot_target_path_uses_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "PSP"
            source.mkdir()
            job = BackupJob(
                id="job-001",
                name="Snapshot Job",
                sources=[str(source)],
                destination=str(root / "backup"),
                mode=BackupMode.SNAPSHOT,
            )

            plans = self.builder.build_source_plans(job, snapshot_stamp="2026-03-22_153000")
            self.assertEqual(len(plans), 1)
            self.assertTrue(plans[0].resolved_target_path.endswith(r"2026-03-22_153000\PSP"))

    def test_mirror_preview_command_includes_dry_run_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "PSP"
            source.mkdir()
            job = BackupJob(
                id="job-001",
                name="Mirror Job",
                sources=[str(source)],
                destination=str(root / "backup"),
                mode=BackupMode.MIRROR,
                exclude_extensions=[".tmp"],
            )

            plans = self.builder.build_source_plans(job)
            self.assertIn("/L", plans[0].preview_command)
            self.assertIn("/MIR", plans[0].run_command)
            self.assertIn("*.tmp", plans[0].run_command)


if __name__ == "__main__":
    unittest.main()
