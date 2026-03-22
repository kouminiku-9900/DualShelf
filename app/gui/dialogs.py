from __future__ import annotations

import os
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from app.core.drive_utils import format_bytes
from app.core.models import BackupJob, PreparedBackup, RunSummary


def open_in_shell(path: str) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", path])


class RunConfirmationDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, job: BackupJob, prepared_backup: PreparedBackup) -> None:
        super().__init__(parent)
        self.title("実行前確認")
        self.transient(parent)
        self.result = False
        self.job = job
        self.prepared_backup = prepared_backup
        self.mirror_phrase_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    @classmethod
    def show_modal(cls, parent: tk.Misc, job: BackupJob, prepared_backup: PreparedBackup) -> bool:
        dialog = cls(parent, job, prepared_backup)
        dialog.grab_set()
        dialog.wait_window()
        return dialog.result

    def _build(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.grid(sticky="nsew")
        container.columnconfigure(0, weight=1)

        summary = tk.Text(container, height=14, wrap="word")
        summary.grid(row=0, column=0, sticky="nsew")
        summary.insert("1.0", self._build_summary_text())
        summary.configure(state="disabled")

        if self.prepared_backup.preflight_report.warnings:
            warning_text = "\n".join(self.prepared_backup.preflight_report.warnings)
            ttk.Label(
                container,
                text=f"警告:\n{warning_text}",
                style="Danger.TLabel" if self.job.mode.value == "mirror" else "TLabel",
                justify="left",
            ).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        if self.job.mode.value == "mirror":
            self._build_mirror_section(container)

        buttons = ttk.Frame(container)
        buttons.grid(row=10, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="中止", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="実行", command=self._confirm).pack(side="right", padx=(0, 8))

    def _build_mirror_section(self, parent: ttk.Frame) -> None:
        report = self.prepared_backup.preflight_report
        summary = report.mirror_preview_summary
        ttk.Separator(parent).grid(row=2, column=0, sticky="ew", pady=(12, 12))
        ttk.Label(
            parent,
            text="元で削除したファイルは先でも削除されます",
            style="Danger.TLabel",
        ).grid(row=3, column=0, sticky="w")
        ttk.Label(
            parent,
            text="実行するには確認欄に MIRROR と入力してください。",
            style="Danger.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(4, 0))

        preview_stats = (
            f"削除候補(EXTRA): {summary.extra_entries if summary else 0}\n"
            f"コピー候補: {summary.candidate_copy_entries if summary else 0}\n"
            f"推定コピーサイズ: {format_bytes(summary.estimated_copy_bytes if summary else None)}"
        )
        ttk.Label(parent, text=preview_stats, justify="left").grid(row=5, column=0, sticky="w", pady=(8, 0))

        preview_box = tk.Text(parent, height=14, wrap="none")
        preview_box.grid(row=6, column=0, sticky="nsew", pady=(8, 0))
        preview_box.insert("1.0", summary.raw_output if summary else "")
        preview_box.configure(state="disabled")

        entry_row = ttk.Frame(parent)
        entry_row.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        entry_row.columnconfigure(1, weight=1)
        ttk.Label(entry_row, text="確認入力").grid(row=0, column=0, sticky="w")
        ttk.Entry(entry_row, textvariable=self.mirror_phrase_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _build_summary_text(self) -> str:
        report = self.prepared_backup.preflight_report
        drive_status = report.drive_status
        lines = [
            f"ジョブ名: {self.job.name}",
            f"モード: {self.job.mode.value}",
            f"バックアップ先: {self.job.destination}",
            f"削除反映: {'あり' if self.job.mode.value == 'mirror' else 'なし'}",
            f"ドライブ: {drive_status.root if drive_status else '不明'}",
            f"総容量: {format_bytes(drive_status.total_bytes if drive_status else None)}",
            f"空き容量: {format_bytes(report.free_bytes)}",
            f"必要容量見積: {format_bytes(report.estimated_required_bytes)}",
            "",
            "コピー計画:",
        ]
        for plan in self.prepared_backup.source_plans:
            lines.append(f"- {plan.source_path}")
            lines.append(f"  -> {plan.resolved_target_path}")
        return "\n".join(lines)

    def _confirm(self) -> None:
        if self.job.mode.value == "mirror" and self.mirror_phrase_var.get().strip() != "MIRROR":
            messagebox.showerror("確認入力エラー", "MIRROR と正確に入力してください。", parent=self)
            return
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()


class RunResultDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, run_summary: RunSummary) -> None:
        super().__init__(parent)
        self.title("実行結果")
        self.transient(parent)
        self.run_summary = run_summary
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    @classmethod
    def show_modal(cls, parent: tk.Misc, run_summary: RunSummary) -> None:
        dialog = cls(parent, run_summary)
        dialog.grab_set()
        dialog.wait_window()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)

        status_label = ttk.Label(frame, text=f"結果: {self.run_summary.overall_status}")
        if self.run_summary.overall_status != "success":
            status_label.configure(style="Danger.TLabel")
        status_label.grid(row=0, column=0, sticky="w")

        text = tk.Text(frame, height=18, wrap="word")
        text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        text.insert("1.0", self._build_summary_text())
        text.configure(state="disabled")

        if self.run_summary.log_warning:
            ttk.Label(frame, text=self.run_summary.log_warning, style="Danger.TLabel").grid(
                row=2,
                column=0,
                sticky="w",
                pady=(8, 0),
            )

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="閉じる", command=self.destroy).pack(side="right")
        if self.run_summary.log_path:
            ttk.Button(
                button_row,
                text="ログを開く",
                command=lambda: open_in_shell(self.run_summary.log_path or ""),
            ).pack(side="right", padx=(0, 8))

    def _build_summary_text(self) -> str:
        lines = [
            f"開始: {self.run_summary.started_at.isoformat(sep=' ', timespec='seconds')}",
            f"終了: {self.run_summary.finished_at.isoformat(sep=' ', timespec='seconds')}",
            f"実行時間: {self.run_summary.elapsed_seconds:.2f} 秒",
            f"エラー件数: {self.run_summary.error_count}",
            f"警告件数: {self.run_summary.warning_count}",
            f"中断件数: {self.run_summary.cancelled_count}",
            "",
            "ソース別結果:",
        ]
        for result in self.run_summary.per_source_results:
            copied = result.copied_files if result.copied_files is not None else "N/A"
            lines.append(
                f"- {result.source_path} -> {result.target_path}\n"
                f"  status={result.status}, exit={result.run_exit_code}, copied={copied}, extra={result.extra_entries}"
            )
        return "\n".join(lines)
