from __future__ import annotations

import shutil
from pathlib import Path

from app.core.models import DriveStatus


def get_drive_root(path_value: str) -> str:
    path = Path(path_value)
    drive = path.drive
    if drive:
        return f"{drive}\\"
    return ""


def get_drive_status(path_value: str) -> DriveStatus:
    root = get_drive_root(path_value)
    if not root:
        return DriveStatus(root="", is_connected=False)

    root_path = Path(root)
    if not root_path.exists():
        return DriveStatus(root=root, is_connected=False)

    try:
        usage = shutil.disk_usage(root_path)
    except OSError:
        return DriveStatus(root=root, is_connected=False)

    return DriveStatus(
        root=root,
        is_connected=True,
        total_bytes=usage.total,
        free_bytes=usage.free,
    )


def format_bytes(value: int | None) -> str:
    if value is None:
        return "不明"

    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024

    return f"{value} B"
