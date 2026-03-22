from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.models import BackupJob, ConfigLoadResult


@dataclass(slots=True)
class AppPaths:
    app_root: Path
    data_root: Path
    jobs_file: Path
    default_log_root: Path
    frozen: bool


def resolve_app_paths(
    *,
    frozen: bool | None = None,
    executable_path: str | Path | None = None,
    module_file: str | Path | None = None,
) -> AppPaths:
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        app_root = Path(executable_path or sys.executable).resolve().parent
    else:
        module_path = Path(module_file or __file__).resolve()
        app_root = module_path.parent.parent

    data_root = app_root / "data"
    return AppPaths(
        app_root=app_root,
        data_root=data_root,
        jobs_file=data_root / "jobs.json",
        default_log_root=data_root / "logs",
        frozen=is_frozen,
    )


class ConfigManager:
    def __init__(self, app_paths: AppPaths | None = None) -> None:
        self.app_paths = app_paths or resolve_app_paths()

    def ensure_storage(self) -> None:
        self.app_paths.data_root.mkdir(parents=True, exist_ok=True)
        self.app_paths.default_log_root.mkdir(parents=True, exist_ok=True)

    def load_jobs(self) -> ConfigLoadResult:
        self.ensure_storage()
        if not self.app_paths.jobs_file.exists():
            return ConfigLoadResult(jobs=[])

        try:
            payload = json.loads(self.app_paths.jobs_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            message = (
                f"設定ファイルの読み込みに失敗しました: {self.app_paths.jobs_file}\n"
                f"JSON が破損している可能性があります。\n"
                f"詳細: {exc}"
            )
            return ConfigLoadResult(jobs=[], error_message=message)

        jobs = [BackupJob.from_dict(item) for item in payload.get("jobs", [])]
        return ConfigLoadResult(jobs=jobs)

    def save_jobs(self, jobs: list[BackupJob]) -> None:
        self.ensure_storage()
        payload = {"jobs": [job.to_dict() for job in jobs]}
        temp_path = self.app_paths.jobs_file.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.app_paths.jobs_file)

    def resolve_user_path(self, user_path: str) -> Path:
        candidate = Path(user_path)
        if candidate.is_absolute():
            return candidate
        return (self.app_paths.app_root / candidate).resolve()
