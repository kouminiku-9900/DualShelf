from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app.core.backup_runner import BackupService
from app.core.config_manager import ConfigManager
from app.core.drive_utils import format_bytes, get_drive_status
from app.core.models import BackupJob, PreparedBackup, ProgressUpdate, RunSummary
from app.gui.dialogs import RunConfirmationDialog, RunResultDialog, open_in_shell
from app.gui.job_editor import JobEditorDialog


class MainWindow(ttk.Frame):
    def __init__(
        self,
        *,
        root: tk.Tk,
        config_manager: ConfigManager,
        backup_service: BackupService,
    ) -> None:
        super().__init__(root, padding=12)
        self.root = root
        self.config_manager = config_manager
        self.backup_service = backup_service

        self.jobs: list[BackupJob] = []
        self.busy = False
        self.status_var = tk.StringVar(value="準備完了")
        self.progress_label_var = tk.StringVar(value="")
        self.active_cancel_event: threading.Event | None = None
        self.cancel_enabled = False
        self._async_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build()
        self._load_jobs()
        self.after(120, self._poll_async_queue)

    def _build(self) -> None:
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(pane, padding=(0, 0, 12, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        pane.add(left, weight=2)

        right = ttk.Frame(pane)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        pane.add(right, weight=3)

        self.job_tree = ttk.Treeview(left, columns=("mode",), show="headings", height=18)
        self.job_tree.heading("mode", text="ジョブ一覧")
        self.job_tree.column("mode", width=280, anchor="w")
        self.job_tree.grid(row=0, column=0, sticky="nsew")
        self.job_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_detail())

        detail_frame = ttk.LabelFrame(right, text="ジョブ詳細", padding=10)
        detail_frame.grid(row=0, column=0, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.detail_text = tk.Text(detail_frame, wrap="word")
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        self.detail_text.configure(state="disabled")

        button_row = ttk.Frame(self)
        button_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.run_button = ttk.Button(button_row, text="実行", command=self._run_selected_job)
        self.run_button.pack(side="left")
        self.create_button = ttk.Button(button_row, text="新規作成", command=self._create_job)
        self.create_button.pack(side="left", padx=(8, 0))
        self.edit_button = ttk.Button(button_row, text="編集", command=self._edit_selected_job)
        self.edit_button.pack(side="left", padx=(8, 0))
        self.delete_button = ttk.Button(button_row, text="削除", command=self._delete_selected_job)
        self.delete_button.pack(side="left", padx=(8, 0))
        self.log_button = ttk.Button(button_row, text="ログを開く", command=self._open_latest_log)
        self.log_button.pack(side="left", padx=(8, 0))
        self.cancel_button = ttk.Button(
            button_row,
            text="キャンセル",
            command=self._request_cancel,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Label(button_row, textvariable=self.status_var).pack(side="right")

        progress_row = ttk.Frame(self)
        progress_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        progress_row.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_row, orient="horizontal", mode="determinate", maximum=1)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_row, textvariable=self.progress_label_var).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _load_jobs(self) -> None:
        result = self.config_manager.load_jobs()
        self.jobs = result.jobs
        self._refresh_job_tree()
        if result.error_message:
            messagebox.showerror("設定読み込みエラー", result.error_message, parent=self.root)

    def _refresh_job_tree(self) -> None:
        selected_id = self._selected_job_id()
        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        for job in self.jobs:
            self.job_tree.insert("", "end", iid=job.id, values=(f"{job.name} [{job.mode.value}]",))

        if selected_id and any(job.id == selected_id for job in self.jobs):
            self.job_tree.selection_set(selected_id)
        elif self.jobs:
            self.job_tree.selection_set(self.jobs[0].id)
        self._update_detail()

    def _selected_job_id(self) -> str | None:
        selection = self.job_tree.selection()
        return selection[0] if selection else None

    def _selected_job(self) -> BackupJob | None:
        selected_id = self._selected_job_id()
        for job in self.jobs:
            if job.id == selected_id:
                return job
        return None

    def _update_detail(self) -> None:
        job = self._selected_job()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        if not job:
            self.detail_text.insert("1.0", "ジョブを選択してください。")
        else:
            self.detail_text.insert("1.0", self._build_job_detail(job))
        self.detail_text.configure(state="disabled")

    def _build_job_detail(self, job: BackupJob) -> str:
        drive_status = get_drive_status(job.destination)
        exclude_dirs = [f"- {item}" for item in job.exclude_dirs] or ["- なし"]
        exclude_extensions = [f"- {item}" for item in job.exclude_extensions] or ["- なし"]
        lines = [
            f"ジョブ名: {job.name}",
            f"モード: {job.mode.value}",
            f"バックアップ先: {job.destination}",
            f"ドライブ状態: {'接続済み' if drive_status.is_connected else '未接続'}",
            f"総容量: {format_bytes(drive_status.total_bytes)}",
            f"空き容量: {format_bytes(drive_status.free_bytes)}",
            f"ログ保存: {'有効' if job.log_enabled else '無効'}",
            f"ログ保存先: {job.log_directory}",
            f"実行前確認: 常に有効",
            "",
            "元フォルダ:",
        ]
        lines.extend(f"- {source}" for source in job.sources)
        lines.extend(["", "除外フォルダ:", *exclude_dirs, "", "除外拡張子:", *exclude_extensions])
        return "\n".join(lines)

    def _create_job(self) -> None:
        if self.busy:
            return
        job = JobEditorDialog.show_modal(self.root, self.backup_service.builder)
        if not job:
            return
        self.jobs.append(job)
        self._persist_jobs()
        self._refresh_job_tree()
        self.job_tree.selection_set(job.id)
        self.status_var.set(f"ジョブを保存しました: {job.name}")

    def _edit_selected_job(self) -> None:
        if self.busy:
            return
        job = self._selected_job()
        if not job:
            messagebox.showinfo("ジョブ未選択", "編集するジョブを選択してください。", parent=self.root)
            return
        updated = JobEditorDialog.show_modal(self.root, self.backup_service.builder, initial_job=job)
        if not updated:
            return
        self.jobs = [updated if item.id == updated.id else item for item in self.jobs]
        self._persist_jobs()
        self._refresh_job_tree()
        self.job_tree.selection_set(updated.id)
        self.status_var.set(f"ジョブを更新しました: {updated.name}")

    def _delete_selected_job(self) -> None:
        if self.busy:
            return
        job = self._selected_job()
        if not job:
            messagebox.showinfo("ジョブ未選択", "削除するジョブを選択してください。", parent=self.root)
            return
        confirmed = messagebox.askyesno(
            "ジョブ削除",
            f"ジョブ '{job.name}' を削除しますか？",
            parent=self.root,
        )
        if not confirmed:
            return
        self.jobs = [item for item in self.jobs if item.id != job.id]
        self._persist_jobs()
        self._refresh_job_tree()
        self.status_var.set(f"ジョブを削除しました: {job.name}")

    def _run_selected_job(self) -> None:
        if self.busy:
            return
        job = self._selected_job()
        if not job:
            messagebox.showinfo("ジョブ未選択", "実行するジョブを選択してください。", parent=self.root)
            return
        self._show_prepare_progress(job.name)
        self._set_busy(True, f"事前確認中: {job.name}")
        self._start_background("prepared", lambda: self.backup_service.prepare_job(job))

    def _open_latest_log(self) -> None:
        job = self._selected_job()
        if not job:
            messagebox.showinfo("ジョブ未選択", "ログを開くジョブを選択してください。", parent=self.root)
            return
        latest = self.backup_service.log_manager.find_latest_log(job)
        if not latest:
            messagebox.showinfo("ログなし", "まだログが保存されていません。", parent=self.root)
            return
        open_in_shell(latest)

    def _persist_jobs(self) -> None:
        try:
            self.config_manager.save_jobs(self.jobs)
        except Exception as exc:
            messagebox.showerror("保存エラー", f"ジョブ保存に失敗しました。\n{exc}", parent=self.root)

    def _set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in [
            self.run_button,
            self.create_button,
            self.edit_button,
            self.delete_button,
            self.log_button,
        ]:
            widget.configure(state=state)
        self.cancel_button.configure(
            state="normal" if busy and self.cancel_enabled else "disabled"
        )
        self.job_tree.configure(selectmode="none" if busy else "browse")
        self.status_var.set(status)

    def _start_background(self, event_name: str, func) -> None:
        def runner() -> None:
            try:
                payload = func()
                self._async_queue.put((event_name, payload))
            except Exception as exc:
                self._async_queue.put(("error", exc))

        threading.Thread(target=runner, daemon=True).start()

    def _poll_async_queue(self) -> None:
        try:
            while True:
                event_name, payload = self._async_queue.get_nowait()
                if event_name == "prepared":
                    self._handle_prepared(payload)  # type: ignore[arg-type]
                elif event_name == "run_complete":
                    self._handle_run_complete(payload)  # type: ignore[arg-type]
                elif event_name == "progress":
                    self._handle_progress(payload)  # type: ignore[arg-type]
                else:
                    self._handle_async_error(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        finally:
            self.after(120, self._poll_async_queue)

    def _handle_prepared(self, prepared_backup: PreparedBackup) -> None:
        self._set_busy(False, "事前確認完了")
        report = prepared_backup.preflight_report
        if report.has_blocking_issues:
            details: list[str] = list(report.blocking_errors)
            if report.missing_sources:
                details.append("")
                details.append("存在しない元フォルダ:")
                details.extend(report.missing_sources)
            if report.drive_status and report.drive_status.root:
                details.append("")
                details.append(f"バックアップ先ドライブ: {report.drive_status.root}")
            message = "\n".join(details)
            if report.warnings:
                message += "\n\n警告:\n" + "\n".join(report.warnings)
            messagebox.showerror("実行前確認エラー", message, parent=self.root)
            self.status_var.set("実行前確認で停止しました")
            self._reset_progress_ui()
            return

        confirmed = RunConfirmationDialog.show_modal(self.root, prepared_backup.job, prepared_backup)
        if not confirmed:
            self.status_var.set("実行を中止しました")
            self._reset_progress_ui()
            return

        self._show_run_progress(prepared_backup)
        self.active_cancel_event = threading.Event()
        self._set_cancel_enabled(True)
        self._set_busy(True, f"バックアップ実行中: {prepared_backup.job.name}")
        self._start_background(
            "run_complete",
            lambda: self.backup_service.run_job(
                prepared_backup,
                progress_callback=lambda update: self._async_queue.put(("progress", update)),
                cancel_event=self.active_cancel_event,
            ),
        )

    def _handle_run_complete(self, run_summary: RunSummary) -> None:
        self._set_busy(False, f"実行完了: {run_summary.overall_status}")
        self._reset_progress_ui()
        RunResultDialog.show_modal(self.root, run_summary)

    def _handle_async_error(self, error: Exception) -> None:
        self._set_busy(False, "エラーが発生しました")
        self._reset_progress_ui()
        messagebox.showerror("処理エラー", str(error), parent=self.root)

    def _show_prepare_progress(self, job_name: str) -> None:
        self.progress_bar.configure(mode="indeterminate", maximum=100)
        self.progress_bar["value"] = 0
        self.progress_bar.start(12)
        self.progress_label_var.set(f"事前確認中: {job_name}")

    def _show_run_progress(self, prepared_backup: PreparedBackup) -> None:
        total = max(1, len(prepared_backup.source_plans))
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=total)
        self.progress_bar["value"] = 0
        self.progress_label_var.set(f"0/{total}: 実行待機")

    def _reset_progress_ui(self) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=1)
        self.progress_bar["value"] = 0
        self.progress_label_var.set("")
        self.active_cancel_event = None
        self._set_cancel_enabled(False)

    def _handle_progress(self, update: ProgressUpdate) -> None:
        total = max(1, update.total_sources)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=total)
        if update.phase == "running":
            self.progress_bar["value"] = max(0, update.current_index - 1)
            self.progress_label_var.set(f"実行中 {update.message}")
        elif update.phase == "completed_source":
            self.progress_bar["value"] = update.current_index
            self.progress_label_var.set(update.message)
        elif update.phase == "cancelled":
            self.progress_bar["value"] = update.current_index
            self.progress_label_var.set(update.message)
        elif update.phase == "finished":
            self.progress_bar["value"] = total
            self.progress_label_var.set(update.message)

    def _set_cancel_enabled(self, enabled: bool) -> None:
        self.cancel_enabled = enabled
        self.cancel_button.configure(
            state="normal" if self.busy and enabled else "disabled"
        )

    def _request_cancel(self) -> None:
        if not self.active_cancel_event or self.active_cancel_event.is_set():
            return
        confirmed = messagebox.askyesno(
            "バックアップを中断",
            "実行中のバックアップを中断します。途中までコピーされた内容は残る可能性があります。\n中断しますか？",
            parent=self.root,
        )
        if not confirmed:
            return
        self.active_cancel_event.set()
        self._set_cancel_enabled(False)
        self.status_var.set("キャンセル要求中...")
        current_label = self.progress_label_var.get().strip()
        if current_label:
            self.progress_label_var.set(f"{current_label} / キャンセル要求中")
        else:
            self.progress_label_var.set("キャンセル要求中")
