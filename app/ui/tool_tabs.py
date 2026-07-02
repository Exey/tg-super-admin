"""Concrete tool tabs."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from ..tools.backup import run_backup
from ..tools.cleaner import run_cleaner
from ..tools.common import reset_progress
from ..tools.repost import run_repost
from ..tools.restore import run_restore
from .base_tab import ToolTab

MAX_ID = 2_147_483_647


def _folder_row(parent, line_edit: QLineEdit, browse_text: str) -> QWidget:
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(line_edit, stretch=1)
    btn = QPushButton(browse_text)

    def pick() -> None:
        path = QFileDialog.getExistingDirectory(parent, browse_text,
                                                line_edit.text() or "")
        if path:
            line_edit.setText(path)

    btn.clicked.connect(pick)
    lay.addWidget(btn)
    return row


# ================================================================== Backup

class BackupTab(ToolTab):
    tool_name = "backup"

    def help_text(self) -> str:
        return self.tr_("backup_help")

    def build_form(self) -> None:
        self.group_edit = QLineEdit(self.cfg.get("CHANNEL_ID"))
        self.form.addRow(self.tr_("backup_group"), self.group_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([self.tr_("mode_all"), self.tr_("mode_media"),
                                  self.tr_("mode_text")])
        self.form.addRow(self.tr_("backup_mode"), self.mode_combo)

        self.min_id = QSpinBox(); self.min_id.setRange(0, MAX_ID)
        self.max_id = QSpinBox(); self.max_id.setRange(0, MAX_ID)
        self.form.addRow(self.tr_("min_id"), self.min_id)
        self.form.addRow(self.tr_("max_id"), self.max_id)

        self.out_edit = QLineEdit(self.cfg.default_backup_dir())
        self.form.addRow(self.tr_("output_folder"),
                         _folder_row(self, self.out_edit, self.tr_("browse")))

    def collect_params(self) -> dict | None:
        if not self.group_edit.text().strip() or not self.out_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("backup_group"))
            return None
        return {
            "group": self.group_edit.text().strip(),
            "mode": self.mode_combo.currentIndex() + 1,
            "min_id": self.min_id.value(),
            "max_id": self.max_id.value(),
            "output_folder": self.out_edit.text().strip(),
        }

    def tool_func(self):
        return run_backup


# ================================================================= Restore

class RestoreTab(ToolTab):
    tool_name = "restore"

    def help_text(self) -> str:
        return self.tr_("restore_help")

    def build_form(self) -> None:
        self.folder_edit = QLineEdit(self.cfg.default_backup_dir())
        self.form.addRow(self.tr_("restore_folder"),
                         _folder_row(self, self.folder_edit, self.tr_("browse")))

        self.chat_edit = QLineEdit(self.cfg.get("CHAT_ID"))
        self.form.addRow(self.tr_("restore_chat"), self.chat_edit)

        self.topic_spin = QSpinBox(); self.topic_spin.setRange(0, MAX_ID)
        try:
            self.topic_spin.setValue(int(self.cfg.get("TOPIC_ID") or 0))
        except ValueError:
            pass
        self.form.addRow(self.tr_("restore_topic"), self.topic_spin)

        self.sep_check = QCheckBox(self.tr_("daily_sep"))
        self.sep_check.setChecked(True)
        self.form.addRow("", self.sep_check)

        self.size_spin = QSpinBox(); self.size_spin.setRange(1, 4000)
        self.size_spin.setValue(50)
        self.form.addRow(self.tr_("max_size"), self.size_spin)

        self.skip_check = QCheckBox(self.tr_("skip_big"))
        self.form.addRow("", self.skip_check)

        self.start_spin = QSpinBox(); self.start_spin.setRange(0, MAX_ID)
        self.form.addRow(self.tr_("start_index"), self.start_spin)

        self.search_edit = QLineEdit()
        self.form.addRow(self.tr_("search_text"), self.search_edit)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 60.0); self.delay_spin.setValue(1.0)
        self.form.addRow(self.tr_("delay"), self.delay_spin)

        reset_btn = QPushButton(self.tr_("reset_progress"))
        reset_btn.clicked.connect(self._reset_progress)
        self.form.addRow("", reset_btn)

    def _reset_progress(self) -> None:
        reset_progress(self.cfg.progress_file(self.tool_name))
        self.append_log(self.tr_("progress_reset"))

    def collect_params(self) -> dict | None:
        if not self.chat_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("restore_chat"))
            return None
        return {
            "backup_folder": self.folder_edit.text().strip(),
            "chat": self.chat_edit.text().strip(),
            "topic_id": self.topic_spin.value(),
            "daily_separator": self.sep_check.isChecked(),
            "max_size_mb": self.size_spin.value(),
            "skip_big": self.skip_check.isChecked(),
            "start_index": self.start_spin.value(),
            "search_text": self.search_edit.text(),
            "delay": self.delay_spin.value(),
            "progress_file": self.cfg.progress_file(self.tool_name),
        }

    def tool_func(self):
        return run_restore


# ================================================================== Repost

class RepostTab(ToolTab):
    tool_name = "repost"

    def help_text(self) -> str:
        return self.tr_("repost_help")

    def build_form(self) -> None:
        self.source_edit = QLineEdit(self.cfg.get("SOURCE_CHANNEL"))
        self.target_edit = QLineEdit(self.cfg.get("TARGET_CHANNEL"))
        self.form.addRow(self.tr_("repost_source"), self.source_edit)
        self.form.addRow(self.tr_("repost_target"), self.target_edit)

        mode_box = QWidget()
        mode_lay = QVBoxLayout(mode_box)
        mode_lay.setContentsMargins(0, 0, 0, 0)
        self.copy_radio = QRadioButton(self.tr_("mode_copy"))
        self.forward_radio = QRadioButton(self.tr_("mode_forward"))
        self.copy_radio.setChecked(True)
        mode_lay.addWidget(self.copy_radio)
        mode_lay.addWidget(self.forward_radio)
        self.form.addRow(self.tr_("repost_mode"), mode_box)

        self.stats_check = QCheckBox(self.tr_("send_stats"))
        self.stats_check.setChecked(True)
        self.form.addRow("", self.stats_check)

        self.delete_check = QCheckBox(self.tr_("delete_original"))
        self.form.addRow("", self.delete_check)
        note = QLabel(self.tr_("delete_original_note"))
        note.setStyleSheet("color: #c0392b;")
        note.setWordWrap(True)
        self.form.addRow("", note)

        self.start_spin = QSpinBox(); self.start_spin.setRange(0, MAX_ID)
        self.form.addRow(self.tr_("start_from_id"), self.start_spin)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 60.0); self.delay_spin.setValue(1.5)
        self.form.addRow(self.tr_("delay"), self.delay_spin)

        reset_btn = QPushButton(self.tr_("reset_progress"))
        reset_btn.clicked.connect(self._reset_progress)
        self.form.addRow("", reset_btn)

    def _reset_progress(self) -> None:
        reset_progress(self.cfg.progress_file(self.tool_name))
        self.append_log(self.tr_("progress_reset"))

    def collect_params(self) -> dict | None:
        if not self.source_edit.text().strip() or not self.target_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("repost_source"))
            return None
        if self.delete_check.isChecked():
            text, ok = QInputDialog.getText(
                self, self.tr_("confirm_title"),
                self.tr_("confirm_delete_prompt"))
            if not ok or text.strip() != self.tr_("confirm_word"):
                QMessageBox.information(self, self.tr_("confirm_title"),
                                        self.tr_("confirm_wrong"))
                return None
        return {
            "source": self.source_edit.text().strip(),
            "target": self.target_edit.text().strip(),
            "mode": "forward" if self.forward_radio.isChecked() else "copy",
            "send_stats": self.stats_check.isChecked(),
            "delete_original": self.delete_check.isChecked(),
            "start_from_id": self.start_spin.value(),
            "delay": self.delay_spin.value(),
            "progress_file": self.cfg.progress_file(self.tool_name),
        }

    def tool_func(self):
        return run_repost


# ================================================================= Cleaner

class CleanerTab(ToolTab):
    tool_name = "cleaner"

    def help_text(self) -> str:
        return self.tr_("cleaner_help")

    def build_form(self) -> None:
        warn = QLabel(self.tr_("cleaner_warning"))
        warn.setStyleSheet("color: #c0392b; font-weight: bold;")
        warn.setWordWrap(True)
        self.form.addRow("", warn)

        self.channel_edit = QLineEdit(self.cfg.get("CHANNEL_ID"))
        self.form.addRow(self.tr_("cleaner_channel"), self.channel_edit)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 100)
        self.batch_spin.setValue(100)
        self.form.addRow(self.tr_("batch_size"), self.batch_spin)

    def collect_params(self) -> dict | None:
        if not self.channel_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("cleaner_channel"))
            return None
        text, ok = QInputDialog.getText(
            self, self.tr_("confirm_title"),
            self.tr_("confirm_delete_prompt"))
        if not ok or text.strip() != self.tr_("confirm_word"):
            QMessageBox.information(self, self.tr_("confirm_title"),
                                    self.tr_("confirm_wrong"))
            return None
        return {
            "channel": self.channel_edit.text().strip(),
            "batch_size": self.batch_spin.value(),
        }

    def tool_func(self):
        return run_cleaner
