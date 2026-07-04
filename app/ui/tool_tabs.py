"""Concrete tool tabs."""
from __future__ import annotations

import json
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..tools.backup import run_backup
from ..tools.cleaner import run_cleaner, scan_keep_candidates
from ..tools.common import reset_progress
from ..tools.repost import run_repost
from ..tools.repost_group import count_repost_group, run_repost_group
from ..tools.restore import run_restore
from .base_tab import ToolTab

MAX_ID = 2_147_483_647


def parse_message_id(text: str) -> int | None:
    """Accept a bare message ID or any t.me link (last numeric path part)."""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    m = re.search(r"t\.me/([^\s?#]+)", text)
    if not m:
        return None
    parts = [seg for seg in m.group(1).split("/") if seg]
    for seg in reversed(parts):  # last numeric segment = message ID
        if seg.isdigit():
            return int(seg)
    return None


def build_post_link(channel_text: str, msg_id: int) -> str:
    """Build a t.me link from whatever is in the channel field."""
    v = channel_text.strip().lstrip("@")
    if v.startswith("-100") and v[4:].isdigit():
        return f"https://t.me/c/{v[4:]}/{msg_id}"
    if v.lstrip("-").isdigit():
        return f"https://t.me/c/{v.lstrip('-')}/{msg_id}"
    return f"https://t.me/{v}/{msg_id}" if v else f"https://t.me/c/0/{msg_id}"


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
        self.cfg.profile["CHANNEL_ID"] = self.group_edit.text().strip()
        self.cfg.save()
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
        self.cfg.profile["CHAT_ID"] = self.chat_edit.text().strip()
        self.cfg.profile["TOPIC_ID"] = (
            str(self.topic_spin.value()) if self.topic_spin.value() else "")
        self.cfg.save()
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
        self.cfg.profile["SOURCE_CHANNEL"] = self.source_edit.text().strip()
        self.cfg.profile["TARGET_CHANNEL"] = self.target_edit.text().strip()
        self.cfg.save()
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


# ============================================================ Repost group

class RepostGroupTab(ToolTab):
    tool_name = "repost_group"

    def help_text(self) -> str:
        return self.tr_("repost_group_help")

    def build_form(self) -> None:
        self.source_edit = QLineEdit(self.cfg.get("REPOST_GROUP_SOURCE"))
        self.form.addRow(self.tr_("repost_group_source"), self.source_edit)

        self.author_edit = QLineEdit(self.cfg.get("REPOST_GROUP_AUTHOR"))
        self.form.addRow(self.tr_("repost_group_author"), self.author_edit)

        self.target_edit = QLineEdit(self.cfg.get("REPOST_GROUP_TARGET"))
        self.form.addRow(self.tr_("repost_group_target"), self.target_edit)

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

    def extra_buttons(self, layout) -> None:
        self.count_btn = QPushButton(self.tr_("count_matches"))
        self.count_btn.clicked.connect(self.on_count)
        layout.addWidget(self.count_btn)

    def set_extra_buttons_enabled(self, enabled: bool) -> None:
        self.count_btn.setEnabled(enabled)

    def _reset_progress(self) -> None:
        reset_progress(self.cfg.progress_file(self.tool_name))
        self.append_log(self.tr_("progress_reset"))

    def _require_source_and_author(self) -> bool:
        if not self.source_edit.text().strip() or not self.author_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("repost_group_need_source_author"))
            return False
        return True

    def _persist_fields(self) -> None:
        self.cfg.profile["REPOST_GROUP_SOURCE"] = self.source_edit.text().strip()
        self.cfg.profile["REPOST_GROUP_AUTHOR"] = self.author_edit.text().strip()
        self.cfg.profile["REPOST_GROUP_TARGET"] = self.target_edit.text().strip()
        self.cfg.save()

    def collect_params(self) -> dict | None:
        if not self._require_source_and_author():
            return None
        if not self.target_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("repost_group_target"))
            return None
        if self.delete_check.isChecked():
            text, ok = QInputDialog.getText(
                self, self.tr_("confirm_title"),
                self.tr_("confirm_delete_prompt"))
            if not ok or text.strip() != self.tr_("confirm_word"):
                QMessageBox.information(self, self.tr_("confirm_title"),
                                        self.tr_("confirm_wrong"))
                return None
        self._persist_fields()
        return {
            "source": self.source_edit.text().strip(),
            "author": self.author_edit.text().strip(),
            "target": self.target_edit.text().strip(),
            "mode": "forward" if self.forward_radio.isChecked() else "copy",
            "send_stats": self.stats_check.isChecked(),
            "delete_original": self.delete_check.isChecked(),
            "start_from_id": self.start_spin.value(),
            "delay": self.delay_spin.value(),
            "progress_file": self.cfg.progress_file(self.tool_name),
        }

    def tool_func(self):
        return run_repost_group

    # --------------------------------------------------------------- count
    def on_count(self) -> None:
        if self.is_running():
            return
        if not self.check_conn():
            return
        if not self._require_source_and_author():
            return
        self._persist_fields()
        params = {
            "source": self.source_edit.text().strip(),
            "author": self.author_edit.text().strip(),
        }
        self.launch(count_repost_group, params)


# ==================================================== Keep-list review dialog

class KeepCandidatesDialog(QDialog):
    """Review window for the Cleaner's "Add from list": one row per resolved
    post — a whole album collapses into a single row — with a checkbox, the
    t.me link, a text preview, and the album ID range if any. Double-click a
    row to open it in Telegram and confirm it's the right post. Only the
    checked rows are added to the keep list on OK."""

    def __init__(self, parent, i18n, channel_text: str, items: list[dict]) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.items = items
        self.setWindowTitle(i18n.tr("keep_list_dialog_title"))
        self.resize(680, 420)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(i18n.tr("keep_list_dialog_hint")))

        toolbar = QHBoxLayout()
        all_btn = QPushButton(i18n.tr("keep_select_all"))
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        toolbar.addWidget(all_btn)
        none_btn = QPushButton(i18n.tr("keep_select_none"))
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        toolbar.addWidget(none_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels([
            "", i18n.tr("keep_col_link"), i18n.tr("keep_col_text"),
            i18n.tr("keep_col_range"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row)

        self._checks: list[QCheckBox] = []
        for row, item in enumerate(items):
            link = build_post_link(channel_text, item["ids"][0])

            check = QCheckBox()
            check.setChecked(True)
            self._checks.append(check)
            holder = QWidget()
            h_lay = QHBoxLayout(holder)
            h_lay.setContentsMargins(0, 0, 0, 0)
            h_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h_lay.addWidget(check)
            self.table.setCellWidget(row, 0, holder)

            link_item = QTableWidgetItem(link)
            link_item.setToolTip(link)
            self.table.setItem(row, 1, link_item)
            self.table.setItem(row, 2, QTableWidgetItem(item.get("text", "")))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("range", "")))
        root.addWidget(self.table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _set_all_checked(self, checked: bool) -> None:
        for cb in self._checks:
            cb.setChecked(checked)

    def _open_row(self, row: int, _col: int) -> None:
        link_item = self.table.item(row, 1)
        if link_item:
            QDesktopServices.openUrl(QUrl(link_item.text()))

    def selected_id_groups(self) -> list[list[int]]:
        return [self.items[row]["ids"] for row, cb in enumerate(self._checks)
                if cb.isChecked()]


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
        self.channel_edit.textChanged.connect(self._refresh_keep_links)
        self.form.addRow(self.tr_("cleaner_channel"), self.channel_edit)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 100)
        self.batch_spin.setValue(100)
        self.form.addRow(self.tr_("batch_size"), self.batch_spin)

        # ------------------------------------------------------ keep list
        keep_box = QWidget()
        keep_lay = QVBoxLayout(keep_box)
        keep_lay.setContentsMargins(0, 0, 0, 0)

        add_row = QHBoxLayout()
        self.keep_input = QLineEdit()
        self.keep_input.setPlaceholderText(self.tr_("keep_placeholder"))
        self.keep_input.returnPressed.connect(self._add_keep)
        add_row.addWidget(self.keep_input, stretch=1)
        add_btn = QPushButton(self.tr_("keep_add"))
        add_btn.clicked.connect(self._add_keep)
        add_row.addWidget(add_btn)
        list_btn = QPushButton(self.tr_("keep_add_list"))
        list_btn.clicked.connect(self._add_keep_from_list)
        add_row.addWidget(list_btn)
        keep_lay.addLayout(add_row)

        self.keep_list = QListWidget()
        self.keep_list.setMaximumHeight(120)
        self.keep_list.itemDoubleClicked.connect(self._open_keep_item)
        keep_lay.addWidget(self.keep_list)

        btn_row = QHBoxLayout()
        open_btn = QPushButton(self.tr_("keep_open"))
        open_btn.clicked.connect(
            lambda: self._open_keep_item(self.keep_list.currentItem()))
        btn_row.addWidget(open_btn)
        rm_btn = QPushButton(self.tr_("keep_remove"))
        rm_btn.clicked.connect(self._remove_keep)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        keep_lay.addLayout(btn_row)

        hint = QLabel(self.tr_("keep_hint"))
        hint.setStyleSheet("color: palette(mid);")
        hint.setWordWrap(True)
        keep_lay.addWidget(hint)

        self.form.addRow(self.tr_("keep_ids"), keep_box)
        self._load_keep_ids()

    # ------------------------------------------------------ keep-list ops
    def keep_ids(self) -> list[int]:
        return [self.keep_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.keep_list.count())]

    def _load_keep_ids(self) -> None:
        raw = self.cfg.get("CLEANER_KEEP_IDS")
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                self._append_item(int(chunk))
        self._refresh_keep_links()

    def _persist_keep_ids(self) -> None:
        self.cfg.profile["CLEANER_KEEP_IDS"] = ",".join(
            str(i) for i in self.keep_ids())
        self.cfg.save()

    def _append_item(self, msg_id: int) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, msg_id)
        self.keep_list.addItem(item)

    def _refresh_keep_links(self) -> None:
        channel = self.channel_edit.text()
        for i in range(self.keep_list.count()):
            item = self.keep_list.item(i)
            msg_id = item.data(Qt.ItemDataRole.UserRole)
            link = build_post_link(channel, msg_id)
            item.setText(f"#{msg_id}  —  {link}")
            item.setToolTip(link)

    def _add_keep(self) -> None:
        msg_id = parse_message_id(self.keep_input.text())
        if msg_id is None:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("keep_invalid"))
            return
        if msg_id in self.keep_ids():
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("keep_duplicate"))
            return
        self._append_item(msg_id)
        self._refresh_keep_links()
        self._persist_keep_ids()
        self.keep_input.clear()

    def _remove_keep(self) -> None:
        row = self.keep_list.currentRow()
        if row >= 0:
            self.keep_list.takeItem(row)
            self._persist_keep_ids()

    def _add_keep_from_list(self) -> None:
        if self.is_running():
            return
        if not self.check_conn():
            return
        channel = self.channel_edit.text().strip()
        if not channel:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("cleaner_channel"))
            return
        text, ok = QInputDialog.getMultiLineText(
            self, self.tr_("keep_list_title"), self.tr_("keep_list_prompt"))
        if not ok or not text.strip():
            return

        ids: list[int] = []
        seen: set[int] = set()
        for token in re.split(r"[\s,]+", text.strip()):
            mid = parse_message_id(token)
            if mid is not None and mid not in seen:
                seen.add(mid)
                ids.append(mid)
        if not ids:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("keep_invalid"))
            return

        self.cfg.profile["CHANNEL_ID"] = channel
        self.cfg.save()
        self.launch(scan_keep_candidates, {"channel": channel, "ids": ids},
                   done_slot=self._on_keep_scan_done)

    def _on_keep_scan_done(self, ok: bool, raw: str) -> None:
        items: list[dict] = []
        if ok:
            try:
                items = json.loads(raw).get("items", [])
            except (ValueError, AttributeError):
                ok = False
        self.on_done(ok, self.tr_("keep_list_found", n=len(items)) if ok else raw)
        if not ok:
            return
        if not items:
            self.append_log(self.tr_("keep_list_empty"))
            return
        dlg = KeepCandidatesDialog(self, self.i18n, self.channel_edit.text(), items)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_keep_selection(dlg.selected_id_groups())

    def _apply_keep_selection(self, groups: list[list[int]]) -> None:
        existing = set(self.keep_ids())
        added = 0
        for ids in groups:
            for mid in ids:
                if mid not in existing:
                    self._append_item(mid)
                    existing.add(mid)
                    added += 1
        self._refresh_keep_links()
        self._persist_keep_ids()
        self.append_log(self.tr_("keep_list_added", n=added))

    def _open_keep_item(self, item) -> None:
        if item is None:
            return
        msg_id = item.data(Qt.ItemDataRole.UserRole)
        QDesktopServices.openUrl(
            QUrl(build_post_link(self.channel_edit.text(), msg_id)))

    # -------------------------------------------------------------- run
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
        self.cfg.profile["CHANNEL_ID"] = self.channel_edit.text().strip()
        self._persist_keep_ids()
        return {
            "channel": self.channel_edit.text().strip(),
            "batch_size": self.batch_spin.value(),
            "keep_ids": self.keep_ids(),
        }

    def tool_func(self):
        return run_cleaner
