from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BackupMode(str, Enum):
    APPEND = "append"
    MIRROR = "mirror"
    SNAPSHOT = "snapshot"

    @classmethod
    def from_value(cls, value: str | None) -> "BackupMode":
        if not value:
            return cls.APPEND
        try:
            return cls(value)
        except ValueError:
            return cls.APPEND


@dataclass(slots=True)
class BackupJob:
    id: str
    name: str
    sources: list[str]
    destination: str
    mode: BackupMode = BackupMode.APPEND
    exclude_dirs: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    use_system_excludes: bool = True
    log_enabled: bool = True
    log_directory: str = r".\data\logs"
    confirm_before_run: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupJob":
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            sources=[str(item).strip() for item in data.get("sources", []) if str(item).strip()],
            destination=str(data.get("destination", "")).strip(),
            mode=BackupMode.from_value(str(data.get("mode", "")).strip()),
            exclude_dirs=[str(item).strip() for item in data.get("exclude_dirs", []) if str(item).strip()],
            exclude_extensions=[
                str(item).strip()
                for item in data.get("exclude_extensions", [])
                if str(item).strip()
            ],
            use_system_excludes=bool(data.get("use_system_excludes", True)),
            log_enabled=bool(data.get("log_enabled", True)),
            log_directory=str(data.get("log_directory", r".\data\logs")).strip() or r".\data\logs",
            confirm_before_run=bool(data.get("confirm_before_run", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sources": list(self.sources),
            "destination": self.destination,
            "mode": self.mode.value,
            "exclude_dirs": list(self.exclude_dirs),
            "exclude_extensions": list(self.exclude_extensions),
            "use_system_excludes": self.use_system_excludes,
            "log_enabled": self.log_enabled,
            "log_directory": self.log_directory,
            "confirm_before_run": self.confirm_before_run,
        }


@dataclass(slots=True)
class DriveStatus:
    root: str
    is_connected: bool
    total_bytes: int | None = None
    free_bytes: int | None = None


@dataclass(slots=True)
class SourcePlan:
    source_path: str
    resolved_target_path: str
    preview_command: list[str] = field(default_factory=list)
    run_command: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourcePreviewResult:
    source_path: str
    target_path: str
    command: list[str]
    exit_code: int | None
    output: str
    status: str


@dataclass(slots=True)
class MirrorPreviewSummary:
    extra_entries: int = 0
    candidate_copy_entries: int = 0
    estimated_copy_bytes: int | None = None
    raw_output: str = ""


@dataclass(slots=True)
class PreflightReport:
    missing_sources: list[str] = field(default_factory=list)
    missing_destination_drive: bool = False
    free_bytes: int | None = None
    estimated_required_bytes: int | None = None
    mirror_preview_summary: MirrorPreviewSummary | None = None
    warnings: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)
    drive_status: DriveStatus | None = None

    @property
    def has_blocking_issues(self) -> bool:
        return bool(self.blocking_errors)


@dataclass(slots=True)
class SourceRunResult:
    source_path: str
    target_path: str
    preview_command: list[str] = field(default_factory=list)
    preview_exit_code: int | None = None
    preview_output: str = ""
    run_command: list[str] = field(default_factory=list)
    run_exit_code: int | None = None
    run_output: str = ""
    duration_seconds: float = 0.0
    status: str = "success"
    error_message: str = ""
    copied_files: int | None = None
    copied_bytes: int | None = None
    extra_entries: int | None = None


@dataclass(slots=True)
class RunSummary:
    started_at: datetime
    finished_at: datetime
    elapsed_seconds: float
    per_source_results: list[SourceRunResult]
    overall_status: str
    log_path: str | None = None
    error_count: int = 0
    warning_count: int = 0
    cancelled_count: int = 0
    log_warning: str = ""


@dataclass(slots=True)
class ProgressUpdate:
    phase: str
    current_index: int
    total_sources: int
    source_path: str = ""
    message: str = ""


@dataclass(slots=True)
class CommandExecutionResult:
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False


@dataclass(slots=True)
class PreparedBackup:
    job: BackupJob
    source_plans: list[SourcePlan]
    preflight_report: PreflightReport
    preview_results: list[SourcePreviewResult] = field(default_factory=list)
    snapshot_stamp: str | None = None


@dataclass(slots=True)
class ConfigLoadResult:
    jobs: list[BackupJob]
    error_message: str | None = None
