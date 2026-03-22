from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from app.core.backup_runner import BackupService, classify_robocopy_exit_code
from app.core.config_manager import AppPaths, ConfigManager
from app.core.log_manager import LogManager
from app.core.models import BackupJob, BackupMode, CommandExecutionResult
from app.core.robocopy_builder import RoboCopyBuilder


class BrokenLogManager(LogManager):
    def write_run_log(self, job, prepared_backup, run_summary):  # type: ignore[override]
        raise OSError("disk full")


class BackupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source_a = self.root / "ArchiveA"
        self.source_b = self.root / "ArchiveB"
        self.destination = self.root / "Backup"
        self.source_a.mkdir()
        self.source_b.mkdir()
        (self.source_a / "file1.bin").write_bytes(b"a" * 16)
        (self.source_b / "file2.bin").write_bytes(b"b" * 24)
        self.destination.mkdir()

        app_paths = AppPaths(
            app_root=self.root,
            data_root=self.root / "data",
            jobs_file=self.root / "data" / "jobs.json",
            default_log_root=self.root / "data" / "logs",
            frozen=False,
        )
        self.config_manager = ConfigManager(app_paths)
        self.config_manager.ensure_storage()
        self.builder = RoboCopyBuilder()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_classify_robocopy_exit_code(self) -> None:
        self.assertEqual(classify_robocopy_exit_code(0), "success")
        self.assertEqual(classify_robocopy_exit_code(4), "warning")
        self.assertEqual(classify_robocopy_exit_code(8), "failure")

    def test_prepare_job_runs_mirror_preview(self) -> None:
        def command_runner(command: list[str], cancel_event: threading.Event | None) -> CommandExecutionResult:
            return CommandExecutionResult(
                returncode=1,
                stdout="*EXTRA File old.bin\nFiles : 10 2 8 0 0 0\nBytes : 1000 200 800 0 0 0",
                stderr="",
            )

        service = BackupService(
            builder=self.builder,
            log_manager=LogManager(self.config_manager),
            command_runner=command_runner,
        )
        job = BackupJob(
            id="job-001",
            name="Mirror Job",
            sources=[str(self.source_a)],
            destination=str(self.destination),
            mode=BackupMode.MIRROR,
        )

        prepared = service.prepare_job(job)
        self.assertFalse(prepared.preflight_report.has_blocking_issues)
        self.assertIsNotNone(prepared.preflight_report.mirror_preview_summary)
        self.assertEqual(prepared.preflight_report.mirror_preview_summary.extra_entries, 1)
        self.assertEqual(prepared.preflight_report.estimated_required_bytes, 200)

    def test_prepare_job_blocks_when_preview_fails(self) -> None:
        def command_runner(command: list[str], cancel_event: threading.Event | None) -> CommandExecutionResult:
            return CommandExecutionResult(
                returncode=8,
                stdout="preview failed",
                stderr="",
            )

        service = BackupService(
            builder=self.builder,
            log_manager=LogManager(self.config_manager),
            command_runner=command_runner,
        )
        job = BackupJob(
            id="job-001",
            name="Mirror Job",
            sources=[str(self.source_a)],
            destination=str(self.destination),
            mode=BackupMode.MIRROR,
        )

        prepared = service.prepare_job(job)
        self.assertTrue(prepared.preflight_report.has_blocking_issues)
        self.assertIn("ミラープレビューに失敗したため実行できません。", prepared.preflight_report.blocking_errors)

    def test_run_job_aggregates_failures_and_handles_log_write_failure(self) -> None:
        def command_runner(command: list[str], cancel_event: threading.Event | None) -> CommandExecutionResult:
            source = command[1]
            if source.endswith("ArchiveA"):
                return CommandExecutionResult(
                    returncode=1,
                    stdout="Files : 3 1 2 0 0 0\nBytes : 50 25 25 0 0 0",
                    stderr="",
                )
            return CommandExecutionResult(
                returncode=8,
                stdout="run failed",
                stderr="",
            )

        service = BackupService(
            builder=self.builder,
            log_manager=BrokenLogManager(self.config_manager),
            command_runner=command_runner,
        )
        job = BackupJob(
            id="job-001",
            name="Append Job",
            sources=[str(self.source_a), str(self.source_b)],
            destination=str(self.destination),
            mode=BackupMode.APPEND,
        )

        prepared = service.prepare_job(job)
        summary = service.run_job(prepared)
        self.assertEqual(summary.overall_status, "failure")
        self.assertEqual(len(summary.per_source_results), 2)
        self.assertEqual(summary.error_count, 1)
        self.assertIn("ログ保存に失敗しました", summary.log_warning)

    def test_run_job_emits_progress_updates(self) -> None:
        def command_runner(command: list[str], cancel_event: threading.Event | None) -> CommandExecutionResult:
            return CommandExecutionResult(
                returncode=1,
                stdout="Files : 3 1 2 0 0 0\nBytes : 50 25 25 0 0 0",
                stderr="",
            )

        service = BackupService(
            builder=self.builder,
            log_manager=LogManager(self.config_manager),
            command_runner=command_runner,
        )
        job = BackupJob(
            id="job-001",
            name="Append Job",
            sources=[str(self.source_a), str(self.source_b)],
            destination=str(self.destination),
            mode=BackupMode.APPEND,
        )
        prepared = service.prepare_job(job)
        updates = []

        summary = service.run_job(prepared, progress_callback=updates.append)

        self.assertEqual(summary.overall_status, "success")
        self.assertEqual([item.phase for item in updates], ["running", "completed_source", "running", "completed_source", "finished"])
        self.assertEqual(updates[-1].message, "完了: success")

    def test_run_job_can_be_cancelled_mid_run(self) -> None:
        def command_runner(command: list[str], cancel_event: threading.Event | None) -> CommandExecutionResult:
            assert cancel_event is not None
            cancel_event.set()
            return CommandExecutionResult(
                returncode=1,
                stdout="partial copy",
                stderr="",
                cancelled=True,
            )

        service = BackupService(
            builder=self.builder,
            log_manager=LogManager(self.config_manager),
            command_runner=command_runner,
        )
        job = BackupJob(
            id="job-001",
            name="Append Job",
            sources=[str(self.source_a), str(self.source_b)],
            destination=str(self.destination),
            mode=BackupMode.APPEND,
        )
        prepared = service.prepare_job(job)
        cancel_event = threading.Event()

        summary = service.run_job(prepared, cancel_event=cancel_event)

        self.assertEqual(summary.overall_status, "cancelled")
        self.assertEqual(summary.cancelled_count, 1)
        self.assertEqual(len(summary.per_source_results), 1)
        self.assertEqual(summary.per_source_results[0].status, "cancelled")


if __name__ == "__main__":
    unittest.main()
