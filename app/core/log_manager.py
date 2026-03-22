from __future__ import annotations

from pathlib import Path

from app.core.config_manager import ConfigManager
from app.core.models import BackupJob, PreparedBackup, RunSummary, SourceRunResult
from app.core.robocopy_builder import format_command


class LogManager:
    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager

    def resolve_log_directory(self, job: BackupJob) -> Path:
        if not job.log_directory.strip():
            return self.config_manager.app_paths.default_log_root

        configured_path = Path(job.log_directory)
        if configured_path.is_absolute():
            return configured_path
        return (self.config_manager.app_paths.app_root / configured_path).resolve()

    def write_run_log(
        self,
        job: BackupJob,
        prepared_backup: PreparedBackup,
        run_summary: RunSummary,
    ) -> str:
        log_directory = self.resolve_log_directory(job) / job.id
        log_directory.mkdir(parents=True, exist_ok=True)
        file_name = run_summary.started_at.strftime("%Y-%m-%d_%H%M%S.log")
        log_path = log_directory / file_name
        log_path.write_text(
            self._build_log_text(job, prepared_backup, run_summary),
            encoding="utf-8",
        )
        return str(log_path)

    def find_latest_log(self, job: BackupJob) -> str | None:
        log_directory = self.resolve_log_directory(job) / job.id
        if not log_directory.exists():
            return None
        log_files = sorted(log_directory.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not log_files:
            return None
        return str(log_files[0])

    def _build_log_text(
        self,
        job: BackupJob,
        prepared_backup: PreparedBackup,
        run_summary: RunSummary,
    ) -> str:
        preflight = prepared_backup.preflight_report
        lines = [
            "Portable Backup Tool Log",
            "=" * 80,
            f"実行日時: {run_summary.started_at.isoformat(sep=' ', timespec='seconds')}",
            f"ジョブ名: {job.name}",
            f"モード: {job.mode.value}",
            f"バックアップ先: {job.destination}",
            f"最終判定: {run_summary.overall_status}",
            f"終了日時: {run_summary.finished_at.isoformat(sep=' ', timespec='seconds')}",
            f"実行時間(秒): {run_summary.elapsed_seconds:.2f}",
            "",
            "Preflight",
            "-" * 80,
            f"空き容量: {preflight.free_bytes if preflight.free_bytes is not None else 'N/A'}",
            f"必要容量見積: {preflight.estimated_required_bytes if preflight.estimated_required_bytes is not None else 'N/A'}",
        ]
        if preflight.warnings:
            lines.append("警告:")
            lines.extend(f"  - {warning}" for warning in preflight.warnings)
        if preflight.blocking_errors:
            lines.append("ブロック要因:")
            lines.extend(f"  - {item}" for item in preflight.blocking_errors)
        lines.append("")

        if preflight.mirror_preview_summary:
            lines.extend(
                [
                    "Mirror Preview Summary",
                    "-" * 80,
                    f"追加コピー候補: {preflight.mirror_preview_summary.candidate_copy_entries}",
                    f"削除候補(EXTRA): {preflight.mirror_preview_summary.extra_entries}",
                    f"推定コピーサイズ: {preflight.mirror_preview_summary.estimated_copy_bytes if preflight.mirror_preview_summary.estimated_copy_bytes is not None else 'N/A'}",
                    "",
                    preflight.mirror_preview_summary.raw_output,
                    "",
                ]
            )

        for result in run_summary.per_source_results:
            lines.extend(self._build_source_section(result))

        return "\n".join(lines).strip() + "\n"

    def _build_source_section(self, result: SourceRunResult) -> list[str]:
        section = [
            "Source Result",
            "-" * 80,
            f"Source: {result.source_path}",
            f"Target: {result.target_path}",
            f"Status: {result.status}",
            f"Run Exit Code: {result.run_exit_code if result.run_exit_code is not None else 'N/A'}",
            f"Duration(秒): {result.duration_seconds:.2f}",
            f"Copied Files: {result.copied_files if result.copied_files is not None else 'N/A'}",
            f"Copied Bytes: {result.copied_bytes if result.copied_bytes is not None else 'N/A'}",
            f"Extra Entries: {result.extra_entries if result.extra_entries is not None else 'N/A'}",
        ]
        if result.preview_command:
            section.extend(
                [
                    f"Preview Command: {format_command(result.preview_command)}",
                    f"Preview Exit Code: {result.preview_exit_code if result.preview_exit_code is not None else 'N/A'}",
                    "Preview Output:",
                    result.preview_output,
                ]
            )
        section.extend(
            [
                f"Run Command: {format_command(result.run_command)}",
                "Run Output:",
                result.run_output,
                "",
            ]
        )
        return section
