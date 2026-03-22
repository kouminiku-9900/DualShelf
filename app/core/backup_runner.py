from __future__ import annotations

import locale
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.drive_utils import get_drive_status
from app.core.log_manager import LogManager
from app.core.models import (
    BackupJob,
    BackupMode,
    CommandExecutionResult,
    MirrorPreviewSummary,
    PreparedBackup,
    PreflightReport,
    ProgressUpdate,
    RunSummary,
    SourcePreviewResult,
    SourceRunResult,
)
from app.core.robocopy_builder import RoboCopyBuilder, detect_duplicate_source_basenames

CommandRunner = Callable[[list[str], threading.Event | None], CommandExecutionResult]
ProgressCallback = Callable[[ProgressUpdate], None]


def classify_robocopy_exit_code(exit_code: int) -> str:
    if exit_code >= 8:
        return "failure"
    if exit_code >= 4:
        return "warning"
    return "success"


class BackupService:
    def __init__(
        self,
        builder: RoboCopyBuilder,
        log_manager: LogManager,
        *,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.builder = builder
        self.log_manager = log_manager
        self.command_runner = command_runner or self._default_command_runner

    def prepare_job(self, job: BackupJob) -> PreparedBackup:
        snapshot_stamp = None
        if job.mode is BackupMode.SNAPSHOT:
            snapshot_stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        report = PreflightReport()
        duplicate_names = detect_duplicate_source_basenames(job.sources)
        if duplicate_names:
            report.blocking_errors.append(
                "同一ジョブに同名フォルダのソースがあります: " + ", ".join(duplicate_names)
            )

        missing_sources = [source for source in job.sources if not Path(source).exists()]
        report.missing_sources.extend(missing_sources)
        if missing_sources:
            report.blocking_errors.append("存在しない元フォルダがあります。")

        drive_status = get_drive_status(job.destination)
        report.drive_status = drive_status
        report.missing_destination_drive = not drive_status.is_connected
        report.free_bytes = drive_status.free_bytes
        if not drive_status.is_connected:
            report.blocking_errors.append("バックアップ先ドライブが未接続です。")

        source_plans = self.builder.build_source_plans(job, snapshot_stamp=snapshot_stamp)
        preview_results: list[SourcePreviewResult] = []

        if job.mode is BackupMode.SNAPSHOT:
            report.estimated_required_bytes = self._estimate_sources_size(job.sources)
            if (
                report.free_bytes is not None
                and report.estimated_required_bytes is not None
                and report.free_bytes < report.estimated_required_bytes
            ):
                report.warnings.append("空き容量が不足する可能性があります。")

        if job.mode is BackupMode.APPEND and report.free_bytes is not None:
            append_upper_bound = self._estimate_sources_size(job.sources)
            if append_upper_bound and report.free_bytes < append_upper_bound:
                report.warnings.append(
                    "追記バックアップでも空き容量が不足する可能性があります。"
                )

        if job.mode is BackupMode.MIRROR and not report.has_blocking_issues:
            preview_results, preview_summary = self._run_mirror_preview(source_plans)
            report.mirror_preview_summary = preview_summary
            report.estimated_required_bytes = preview_summary.estimated_copy_bytes
            if preview_summary.extra_entries:
                report.warnings.append(
                    "削除対象または余剰項目(EXTRA)が検出されました。内容を確認してください。"
                )
            if any(result.exit_code is None or result.exit_code >= 8 for result in preview_results):
                report.blocking_errors.append("ミラープレビューに失敗したため実行できません。")

        return PreparedBackup(
            job=job,
            source_plans=source_plans,
            preflight_report=report,
            preview_results=preview_results,
            snapshot_stamp=snapshot_stamp,
        )

    def run_job(
        self,
        prepared_backup: PreparedBackup,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> RunSummary:
        report = prepared_backup.preflight_report
        if report.has_blocking_issues:
            raise ValueError("Blocking preflight issues exist.")

        started_at = datetime.now()
        results: list[SourceRunResult] = []
        preview_lookup = {result.source_path: result for result in prepared_backup.preview_results}
        total_sources = len(prepared_backup.source_plans)
        run_cancelled = False

        for index, plan in enumerate(prepared_backup.source_plans, start=1):
            if cancel_event and cancel_event.is_set():
                run_cancelled = True
                break

            preview_result = preview_lookup.get(plan.source_path)
            start = time.perf_counter()
            target_path = Path(plan.resolved_target_path)
            target_path.mkdir(parents=True, exist_ok=True)
            self._notify_progress(
                progress_callback,
                ProgressUpdate(
                    phase="running",
                    current_index=index,
                    total_sources=total_sources,
                    source_path=plan.source_path,
                    message=f"{index}/{total_sources}: {plan.source_path}",
                ),
            )

            try:
                completed = self.command_runner(plan.run_command, cancel_event)
                output = self._join_output(completed.stdout, completed.stderr)
                status = "cancelled" if completed.cancelled else classify_robocopy_exit_code(completed.returncode or 0)
                summary = self._extract_summary(output)
                result = SourceRunResult(
                    source_path=plan.source_path,
                    target_path=plan.resolved_target_path,
                    preview_command=preview_result.command if preview_result else [],
                    preview_exit_code=preview_result.exit_code if preview_result else None,
                    preview_output=preview_result.output if preview_result else "",
                    run_command=plan.run_command,
                    run_exit_code=completed.returncode,
                    run_output=output,
                    duration_seconds=time.perf_counter() - start,
                    status=status,
                    error_message="ユーザーがキャンセルしました。" if completed.cancelled else "",
                    copied_files=summary.get("copied_files"),
                    copied_bytes=summary.get("copied_bytes"),
                    extra_entries=summary.get("extra_entries"),
                )
                if completed.cancelled:
                    run_cancelled = True
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                result = SourceRunResult(
                    source_path=plan.source_path,
                    target_path=plan.resolved_target_path,
                    preview_command=preview_result.command if preview_result else [],
                    preview_exit_code=preview_result.exit_code if preview_result else None,
                    preview_output=preview_result.output if preview_result else "",
                    run_command=plan.run_command,
                    duration_seconds=time.perf_counter() - start,
                    status="failure",
                    error_message=str(exc),
                    run_output=str(exc),
                )
            results.append(result)
            if result.status == "cancelled":
                self._notify_progress(
                    progress_callback,
                    ProgressUpdate(
                        phase="cancelled",
                        current_index=index,
                        total_sources=total_sources,
                        source_path=plan.source_path,
                        message=f"{index}/{total_sources} 中断: {plan.source_path}",
                    ),
                )
                break
            self._notify_progress(
                progress_callback,
                ProgressUpdate(
                    phase="completed_source",
                    current_index=index,
                    total_sources=total_sources,
                    source_path=plan.source_path,
                    message=f"{index}/{total_sources} 完了: {plan.source_path}",
                ),
            )

        finished_at = datetime.now()
        run_summary = RunSummary(
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=(finished_at - started_at).total_seconds(),
            per_source_results=results,
            overall_status=self._aggregate_status(results, run_cancelled),
            error_count=sum(1 for item in results if item.status == "failure"),
            warning_count=sum(1 for item in results if item.status == "warning"),
            cancelled_count=sum(1 for item in results if item.status == "cancelled"),
        )
        if prepared_backup.job.log_enabled:
            try:
                run_summary.log_path = self.log_manager.write_run_log(
                    prepared_backup.job,
                    prepared_backup,
                    run_summary,
                )
            except Exception as exc:  # pragma: no cover - IO boundary
                run_summary.log_warning = f"ログ保存に失敗しました: {exc}"
                if run_summary.overall_status == "success":
                    run_summary.overall_status = "warning"
                    run_summary.warning_count += 1

        self._notify_progress(
            progress_callback,
            ProgressUpdate(
                phase="finished",
                current_index=total_sources,
                total_sources=total_sources,
                message=f"完了: {run_summary.overall_status}",
            ),
        )
        return run_summary

    def _run_mirror_preview(
        self,
        source_plans: list,
    ) -> tuple[list[SourcePreviewResult], MirrorPreviewSummary]:
        preview_results: list[SourcePreviewResult] = []
        combined_output: list[str] = []
        extra_entries = 0
        copy_candidates = 0
        estimated_bytes: int | None = 0

        for plan in source_plans:
            try:
                completed = self.command_runner(plan.preview_command, None)
                output = self._join_output(completed.stdout, completed.stderr)
                status = "cancelled" if completed.cancelled else classify_robocopy_exit_code(completed.returncode or 0)
            except Exception as exc:  # pragma: no cover - IO boundary
                output = str(exc)
                completed = None
                status = "failure"

            preview_results.append(
                SourcePreviewResult(
                    source_path=plan.source_path,
                    target_path=plan.resolved_target_path,
                    command=plan.preview_command,
                    exit_code=completed.returncode if completed else None,
                    output=output,
                    status=status,
                )
            )

            combined_output.append(f"[{plan.source_path} -> {plan.resolved_target_path}]")
            combined_output.append(output.strip())
            combined_output.append("")

            summary = self._extract_summary(output)
            extra_entries += summary.get("extra_entries", 0) or 0
            copy_candidates += summary.get("copied_files", 0) or 0
            copied_bytes = summary.get("copied_bytes")
            if copied_bytes is None:
                estimated_bytes = None
            elif estimated_bytes is not None:
                estimated_bytes += copied_bytes

        preview_summary = MirrorPreviewSummary(
            extra_entries=extra_entries,
            candidate_copy_entries=copy_candidates,
            estimated_copy_bytes=estimated_bytes,
            raw_output="\n".join(line for line in combined_output if line is not None).strip(),
        )
        return preview_results, preview_summary

    def _aggregate_status(self, results: list[SourceRunResult], run_cancelled: bool) -> str:
        if any(item.status == "failure" for item in results):
            return "failure"
        if run_cancelled or any(item.status == "cancelled" for item in results):
            return "cancelled"
        if any(item.status == "warning" for item in results):
            return "warning"
        return "success"

    def _estimate_sources_size(self, sources: list[str]) -> int | None:
        total = 0
        try:
            for source in sources:
                total += self._estimate_path_size(Path(source))
        except OSError:
            return None
        return total

    def _estimate_path_size(self, path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        stack = [path]
        while stack:
            current = stack.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            continue
        return total

    def _extract_summary(self, output: str) -> dict[str, int | None]:
        copied_files = None
        copied_bytes = None
        extra_entries = len(re.findall(r"^\s*\*EXTRA", output, flags=re.MULTILINE))

        file_match = re.search(
            r"^\s*(?:Files|ファイル)\s*:\s*[\d,]+\s+([\d,]+)",
            output,
            flags=re.MULTILINE,
        )
        if file_match:
            copied_files = self._parse_int(file_match.group(1))
        else:
            candidate_lines = re.findall(
                r"^\s*(?:New File|New Dir|Newer|Older|Changed|Tweaked)\b",
                output,
                flags=re.MULTILINE,
            )
            if candidate_lines:
                copied_files = len(candidate_lines)

        byte_match = re.search(
            r"^\s*(?:Bytes|バイト)\s*:\s*[\d,]+\s+([\d,]+)",
            output,
            flags=re.MULTILINE,
        )
        if byte_match:
            copied_bytes = self._parse_int(byte_match.group(1))

        return {
            "copied_files": copied_files,
            "copied_bytes": copied_bytes,
            "extra_entries": extra_entries,
        }

    def _parse_int(self, value: str) -> int | None:
        stripped = value.replace(",", "").strip()
        if not stripped.isdigit():
            return None
        return int(stripped)

    def _default_command_runner(
        self,
        command: list[str],
        cancel_event: threading.Event | None = None,
    ) -> CommandExecutionResult:
        encoding = locale.getpreferredencoding(False) or "utf-8"
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=encoding,
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        while True:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                return CommandExecutionResult(
                    returncode=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                    cancelled=True,
                )

            try:
                stdout, stderr = process.communicate(timeout=0.2)
                return CommandExecutionResult(
                    returncode=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                    cancelled=False,
                )
            except subprocess.TimeoutExpired:
                continue

    def _join_output(self, stdout: str | None, stderr: str | None) -> str:
        parts = [part.strip() for part in (stdout, stderr) if part and part.strip()]
        return "\n\n".join(parts)

    def _notify_progress(
        self,
        progress_callback: ProgressCallback | None,
        update: ProgressUpdate,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(update)
