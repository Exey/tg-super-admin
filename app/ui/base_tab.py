"""Base class for the four tool tabs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
    QWidget,
)

from ..worker import ToolWorker


class ToolTab(QWidget):
    tool_name = "tool"  # override; used for the progress file name

    def __init__(self, cfg, i18n, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.i18n = i18n
        self.worker: ToolWorker | None = None

        root = QVBoxLayout(self)

        self.help_label = QLabel(self.help_text())
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: palette(mid);")
        root.addWidget(self.help_label)

        self.form = QFormLayout()
        root.addLayout(self.form)
        self.build_form()  # subclass fills self.form

        buttons = QHBoxLayout()
        self.run_btn = QPushButton(self.tr_("run"))
        self.stop_btn = QPushButton(self.tr_("stop"))
        self.stop_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.on_run)
        self.stop_btn.clicked.connect(self.on_stop)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.stop_btn)
        buttons.addStretch()
        root.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)

        root.addWidget(QLabel(self.tr_("log")))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        root.addWidget(self.log_view, stretch=1)

    # -------------------------------------------------- subclass interface
    def tr_(self, key: str, **kw) -> str:
        return self.i18n.tr(key, **kw)

    def help_text(self) -> str:
        return ""

    def build_form(self) -> None:
        raise NotImplementedError

    def collect_params(self) -> dict | None:
        """Return tool params, or None to abort (e.g. failed confirmation)."""
        raise NotImplementedError

    def tool_func(self):
        raise NotImplementedError

    # --------------------------------------------------------- run control
    def is_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def on_run(self) -> None:
        if self.is_running():
            return
        api_id = self.cfg.get("API_ID").strip()
        api_hash = self.cfg.get("API_HASH").strip()
        phone = self.cfg.get("PHONE_NUMBER").strip()
        if not (api_id and api_hash and phone):
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("missing_conn"))
            return

        params = self.collect_params()
        if params is None:
            return

        conn = {
            "api_id": api_id,
            "api_hash": api_hash,
            "phone": phone,
            "session": self.cfg.session_path(),
        }
        self.worker = ToolWorker(self.tool_func(), params, conn, parent=self)
        self.worker.sig_log.connect(self.append_log)
        self.worker.sig_progress.connect(self.on_progress)
        self.worker.sig_done.connect(self.on_done)
        self.worker.sig_ask.connect(self.on_ask)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setRange(0, 0)  # busy until first progress signal
        self.worker.start()

    def on_stop(self) -> None:
        if self.worker:
            self.append_log(self.tr_("cancelled"))
            self.worker.request_cancel()
            self.stop_btn.setEnabled(False)

    # ------------------------------------------------------------- signals
    def append_log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)  # indeterminate

    def on_done(self, ok: bool, msg: str) -> None:
        self.append_log(self.tr_("done_ok" if ok else "done_fail", msg=msg))
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if ok else 0)
        self.worker = None

    def on_ask(self, kind: str, _prompt: str) -> None:
        """Login prompt bridge (runs on the GUI thread)."""
        if kind == "password":
            prompt = self.tr_("login_password_prompt")
            echo = QLineEdit.EchoMode.Password
        else:
            prompt = self.tr_("login_code_prompt")
            echo = QLineEdit.EchoMode.Normal
        text, ok = QInputDialog.getText(
            self, self.tr_("login_title"), prompt, echo
        )
        if not self.worker:
            return
        if ok and text.strip():
            self.worker.provide_answer(text.strip())
        else:
            self.worker.request_cancel()
