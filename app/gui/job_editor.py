from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

from app.core.drive_utils import get_drive_status
from app.core.models import BackupJob, BackupMode
from app.core.robocopy_builder import RoboCopyBuilder, detect_duplicate_source_basenames

MODE_LABELS = {
    BackupMode.APPEND: "追記バックアップ",
    BackupMode.MIRROR: "ミラー同期",
    BackupMode.SNAPSHOT: "スナップショット",
}
MODE_FROM_LABEL = {label: mode for mode, label in MODE_LABELS.items()}


class JobEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        builder: RoboCopyBuilder,
        *,
        initial_job: BackupJob | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("ジョブ編集")
        self.transient(parent)
        self.builder = builder
        self.initial_job = initial_job
        self.result: BackupJob | None = None

        self.name_var = tk.StringVar(value=initial_job.name if initial_job else "")
        self.destination_var = tk.StringVar(value=initial_job.destination if initial_job else "")
        self.mode_var = tk.StringVar(
            value=MODE_LABELS[initial_job.mode] if initial_job else MODE_LABELS[BackupMode.APPEND]
        )
        self.use_system_excludes_var = tk.BooleanVar(
            value=initial_job.use_system_excludes if initial_job else True
        )
        self.log_enabled_var = tk.BooleanVar(value=initial_job.log_enabled if initial_job else True)
        self.log_directory_var = tk.StringVar(
            value=initial_job.log_directory if initial_job else r".\data\logs"
        )

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())

    @classmethod
    def show_modal(
        cls,
        parent: tk.Misc,
        builder: RoboCopyBuilder,
        *,
        initial_job: BackupJob | None = None,
    ) -> BackupJob | None:
        dialog = cls(parent, builder, initial_job=initial_job)
        dialog.grab_set()
        dialog.wait_window()
        return dialog.result

    def _build(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.grid(sticky="nsew")
        container.columnconfigure(0, weight=1)

        basic = ttk.LabelFrame(container, text="基本設定", padding=10)
        basic.grid(row=0, column=0, sticky="ew")
        basic.columnconfigure(1, weight=1)
        ttk.Label(basic, text="ジョブ名").grid(row=0, column=0, sticky="w")
        ttk.Entry(basic, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(basic, text="バックアップ先").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.destination_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Button(basic, text="参照", command=self._browse_destination).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        ttk.Label(basic, text="モード").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            basic,
            textvariable=self.mode_var,
            values=list(MODE_FROM_LABEL.keys()),
            state="readonly",
        ).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        source_frame = ttk.LabelFrame(container, text="元フォルダ", padding=10)
        source_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        source_frame.columnconfigure(0, weight=1)
        self.source_list = tk.Listbox(source_frame, height=6)
        self.source_list.grid(row=0, column=0, sticky="nsew")
        for source in self.initial_job.sources if self.initial_job else []:
            self.source_list.insert("end", source)

        source_buttons = ttk.Frame(source_frame)
        source_buttons.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        ttk.Button(source_buttons, text="追加", command=self._add_source).pack(fill="x")
        ttk.Button(source_buttons, text="削除", command=self._remove_source).pack(fill="x", pady=(8, 0))

        exclude_frame = ttk.LabelFrame(container, text="除外設定", padding=10)
        exclude_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        exclude_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            exclude_frame,
            text="定番システム除外を使う",
            variable=self.use_system_excludes_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(exclude_frame, text="除外フォルダ").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.exclude_dirs_text = tk.Text(exclude_frame, height=4, width=40)
        self.exclude_dirs_text.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.exclude_dirs_text.insert(
            "1.0",
            "\n".join(self.initial_job.exclude_dirs) if self.initial_job else "",
        )
        ttk.Label(exclude_frame, text="除外拡張子").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.exclude_ext_entry = ttk.Entry(exclude_frame)
        self.exclude_ext_entry.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        if self.initial_job:
            self.exclude_ext_entry.insert(0, ", ".join(self.initial_job.exclude_extensions))

        log_frame = ttk.LabelFrame(container, text="ログ設定", padding=10)
        log_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        log_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            log_frame,
            text="ログを保存する",
            variable=self.log_enabled_var,
            command=self._toggle_log_widgets,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(log_frame, text="ログ保存先").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.log_dir_entry = ttk.Entry(log_frame, textvariable=self.log_directory_var)
        self.log_dir_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.log_dir_button = ttk.Button(log_frame, text="参照", command=self._browse_log_directory)
        self.log_dir_button.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        button_row = ttk.Frame(container)
        button_row.grid(row=4, column=0, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="キャンセル", command=self._cancel).pack(side="right")
        ttk.Button(button_row, text="保存", command=self._save).pack(side="right", padx=(0, 8))
        self._toggle_log_widgets()

    def _add_source(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="元フォルダを選択")
        if selected:
            self.source_list.insert("end", selected)

    def _remove_source(self) -> None:
        selection = self.source_list.curselection()
        if selection:
            self.source_list.delete(selection[0])

    def _browse_destination(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="バックアップ先を選択")
        if selected:
            self.destination_var.set(selected)

    def _browse_log_directory(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="ログ保存先を選択")
        if selected:
            self.log_directory_var.set(selected)

    def _toggle_log_widgets(self) -> None:
        state = "normal" if self.log_enabled_var.get() else "disabled"
        self.log_dir_entry.configure(state=state)
        self.log_dir_button.configure(state=state)

    def _save(self) -> None:
        try:
            job = self._build_job()
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc), parent=self)
            return

        destination_status = get_drive_status(job.destination)
        if job.destination and not destination_status.is_connected:
            should_save = messagebox.askyesno(
                "未接続ドライブ",
                "バックアップ先ドライブが現在未接続です。このまま保存しますか？",
                parent=self,
            )
            if not should_save:
                return

        if job.log_enabled and Path(job.log_directory).is_absolute():
            log_status = get_drive_status(job.log_directory)
            if not log_status.is_connected:
                should_save = messagebox.askyesno(
                    "未接続ログ保存先",
                    "ログ保存先ドライブが現在未接続です。このまま保存しますか？",
                    parent=self,
                )
                if not should_save:
                    return

        self.result = job
        self.destroy()

    def _build_job(self) -> BackupJob:
        name = self.name_var.get().strip()
        destination = self.destination_var.get().strip()
        sources = [self.source_list.get(index) for index in range(self.source_list.size())]

        if not name:
            raise ValueError("ジョブ名を入力してください。")
        if not sources:
            raise ValueError("元フォルダを1件以上追加してください。")
        if not destination:
            raise ValueError("バックアップ先を指定してください。")
        if not Path(destination).is_absolute():
            raise ValueError("バックアップ先は絶対パスで指定してください。")

        missing_sources = [source for source in sources if not Path(source).exists()]
        if missing_sources:
            raise ValueError("存在しない元フォルダがあります。")

        duplicate_names = detect_duplicate_source_basenames(sources)
        if duplicate_names:
            raise ValueError("同名フォルダのソースは同一ジョブに登録できません。")

        exclude_dirs = [line.strip() for line in self.exclude_dirs_text.get("1.0", "end").splitlines() if line.strip()]
        exclude_extensions = [
            part.strip()
            for part in re.split(r"[,\r\n]+", self.exclude_ext_entry.get())
            if part.strip()
        ]

        mode = MODE_FROM_LABEL[self.mode_var.get()]
        log_directory = self.log_directory_var.get().strip() or r".\data\logs"
        return BackupJob(
            id=self.initial_job.id if self.initial_job else f"job-{uuid4().hex[:8]}",
            name=name,
            sources=sources,
            destination=destination,
            mode=mode,
            exclude_dirs=exclude_dirs,
            exclude_extensions=exclude_extensions,
            use_system_excludes=self.use_system_excludes_var.get(),
            log_enabled=self.log_enabled_var.get(),
            log_directory=log_directory,
            confirm_before_run=True,
        )

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
