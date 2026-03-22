from __future__ import annotations

import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from app.core.backup_runner import BackupService
from app.core.config_manager import ConfigManager
from app.core.log_manager import LogManager
from app.core.robocopy_builder import RoboCopyBuilder
from app.gui.main_window import MainWindow

APP_VERSION = "v0.3"


def create_root() -> tk.Tk:
    root = tk.Tk()
    root.title(f"Portable Backup Tool {APP_VERSION}")
    root.geometry("1120x720")
    root.minsize(980, 640)

    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    style.configure("Danger.TLabel", foreground="#9d1c1c")
    return root


def install_exception_hook(root: tk.Tk) -> None:
    def report_callback_exception(exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        messagebox.showerror("予期しないエラー", details, parent=root)

    root.report_callback_exception = report_callback_exception


def main() -> None:
    root = create_root()
    install_exception_hook(root)

    config_manager = ConfigManager()
    config_manager.ensure_storage()
    service = BackupService(
        builder=RoboCopyBuilder(),
        log_manager=LogManager(config_manager),
    )
    window = MainWindow(
        root=root,
        config_manager=config_manager,
        backup_service=service,
    )
    window.pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
