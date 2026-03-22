from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.models import BackupJob, BackupMode, SourcePlan

SYSTEM_EXCLUDE_DIRS = ("$RECYCLE.BIN", "System Volume Information")
SYSTEM_EXCLUDE_FILES = ("Thumbs.db", "desktop.ini")


def detect_duplicate_source_basenames(sources: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for source in sources:
        name = Path(source).name.strip().lower()
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    return sorted(name for name, count in counts.items() if count > 1)


def normalize_extension_patterns(extensions: list[str]) -> list[str]:
    normalized: list[str] = []
    for extension in extensions:
        item = extension.strip()
        if not item:
            continue
        if "*" in item or "?" in item:
            normalized.append(item)
            continue
        if item.startswith("."):
            normalized.append(f"*{item}")
            continue
        normalized.append(f"*.{item.lstrip('.')}")
    return normalized


def resolve_target_path(
    source_path: str,
    destination_root: str,
    mode: BackupMode,
    snapshot_stamp: str | None = None,
) -> str:
    source_name = Path(source_path).name
    destination = Path(destination_root)
    if mode is BackupMode.SNAPSHOT:
        if not snapshot_stamp:
            raise ValueError("Snapshot mode requires a snapshot timestamp.")
        return str(destination / snapshot_stamp / source_name)
    return str(destination / source_name)


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


class RoboCopyBuilder:
    def build_source_plans(
        self,
        job: BackupJob,
        *,
        snapshot_stamp: str | None = None,
    ) -> list[SourcePlan]:
        plans: list[SourcePlan] = []
        for source_path in job.sources:
            target_path = resolve_target_path(
                source_path=source_path,
                destination_root=job.destination,
                mode=job.mode,
                snapshot_stamp=snapshot_stamp,
            )
            run_command = self.build_command(
                job=job,
                source_path=source_path,
                target_path=target_path,
                preview=False,
            )
            preview_command = []
            if job.mode is BackupMode.MIRROR:
                preview_command = self.build_command(
                    job=job,
                    source_path=source_path,
                    target_path=target_path,
                    preview=True,
                )
            plans.append(
                SourcePlan(
                    source_path=source_path,
                    resolved_target_path=target_path,
                    preview_command=preview_command,
                    run_command=run_command,
                )
            )
        return plans

    def build_command(
        self,
        *,
        job: BackupJob,
        source_path: str,
        target_path: str,
        preview: bool,
    ) -> list[str]:
        command = ["robocopy", source_path, target_path]
        command.extend(self._mode_flags(job.mode))
        command.extend(["/R:1", "/W:1", "/FFT", "/XJ", "/NP"])
        if preview:
            command.append("/L")
        command.extend(self._exclude_flags(job))
        return command

    def _mode_flags(self, mode: BackupMode) -> list[str]:
        if mode is BackupMode.MIRROR:
            return ["/MIR"]
        return ["/E"]

    def _exclude_flags(self, job: BackupJob) -> list[str]:
        exclude_dirs = list(job.exclude_dirs)
        exclude_files = normalize_extension_patterns(job.exclude_extensions)
        if job.use_system_excludes:
            exclude_dirs.extend(SYSTEM_EXCLUDE_DIRS)
            exclude_files.extend(SYSTEM_EXCLUDE_FILES)

        flags: list[str] = []
        if exclude_dirs:
            flags.append("/XD")
            flags.extend(self._dedupe(exclude_dirs))
        if exclude_files:
            flags.append("/XF")
            flags.extend(self._dedupe(exclude_files))
        return flags

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(value)
        return ordered
