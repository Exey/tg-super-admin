"""Concrete tool tabs."""
from __future__ import annotations

import json
import os
import re

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..tools.backup import run_backup
from ..tools.chat_activity import PERIODS, run_chat_activity
from ..tools.cleaner import run_cleaner, scan_keep_candidates
from ..tools.common import reset_progress
from ..tools.links_compare import (
    exclude_by_md, parse_loadable_rows, populate_followers,
    populate_private_channels, scan_channel_links,
)
from ..tools.post_image_replacer import run_post_image_replace
from ..tools.repost import run_repost
from ..tools.repost_group import count_repost_group, run_repost_group
from ..tools.restore import run_restore
from ..tools.users_extractor import add_users_to_group, run_users_extractor
from ..worker import LocalTaskWorker
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


IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All files (*)"


def _image_file_row(parent, line_edit: QLineEdit, browse_text: str) -> QWidget:
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(line_edit, stretch=1)
    btn = QPushButton(browse_text)

    def pick() -> None:
        path, _ = QFileDialog.getOpenFileName(parent, browse_text,
                                              line_edit.text() or "", IMAGE_FILTER)
        if path:
            line_edit.setText(path)

    btn.clicked.connect(pick)
    lay.addWidget(btn)
    return row


MD_FILTER = "Markdown (*.md);;All files (*)"
JSON_FILTER = "JSON (*.json);;All files (*)"


def _open_file_row(parent, line_edit: QLineEdit, browse_text: str,
                   file_filter: str) -> QWidget:
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(line_edit, stretch=1)
    btn = QPushButton(browse_text)

    def pick() -> None:
        path, _ = QFileDialog.getOpenFileName(parent, browse_text,
                                              line_edit.text() or "", file_filter)
        if path:
            line_edit.setText(path)

    btn.clicked.connect(pick)
    lay.addWidget(btn)
    return row


def parse_id_ranges(text: str) -> list[int]:
    """Parse a free-form list of message IDs: bare IDs, "100-110" ranges,
    and t.me links, separated by commas/whitespace/newlines. Order-preserving,
    de-duplicated."""
    ids: list[int] = []
    seen: set[int] = set()
    for token in re.split(r"[\s,]+", text.strip()):
        if not token:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            span = range(lo, hi + 1)
        else:
            mid = parse_message_id(token)
            span = [mid] if mid is not None else []
        for i in span:
            if i not in seen:
                seen.add(i)
                ids.append(i)
    return ids


def build_user_link(member: dict) -> str:
    username = member.get("username")
    if username:
        return f"https://t.me/{username}"
    return f"tg://user?id={member['id']}"


def render_users_html(title: str, sections: list[tuple[str, list[dict]]]) -> str:
    """One HTML page with a <ul> per section, each user linking to Telegram."""
    from html import escape

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{escape(title)}</title>",
        "<style>body{font-family:sans-serif;margin:2rem;color:#1a1a1a;}"
        "h2{margin-top:2rem;}ul{padding-left:1.2rem;}li{margin:0.25rem 0;}"
        "a{color:#2b6cb0;text-decoration:none;}a:hover{text-decoration:underline;}"
        ".muted{color:#666;font-size:0.9em;}</style></head><body>",
        f"<h1>{escape(title)}</h1>",
    ]
    for name, members in sections:
        parts.append(f"<h2>{escape(name)} ({len(members)})</h2>")
        if not members:
            parts.append("<p class='muted'>—</p>")
            continue
        parts.append("<ul>")
        for m in members:
            link = escape(build_user_link(m), quote=True)
            label = escape(m.get("name") or str(m["id"]))
            tag = f"@{m['username']}" if m.get("username") else f"#{m['id']}"
            parts.append(f"<li><a href='{link}'>{label}</a> "
                        f"<span class='muted'>({escape(tag)})</span></li>")
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


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
        rm_all_btn = QPushButton(self.tr_("keep_remove_all"))
        rm_all_btn.clicked.connect(self._remove_all_keep)
        btn_row.addWidget(rm_all_btn)
        btn_row.addStretch()
        keep_lay.addLayout(btn_row)

        hint = QLabel(self.tr_("keep_hint"))
        hint.setStyleSheet("color: palette(placeholder-text);")
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

    def _remove_all_keep(self) -> None:
        if self.keep_list.count() == 0:
            return
        reply = QMessageBox.question(
            self, self.tr_("app_title"), self.tr_("keep_remove_all_confirm"))
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.keep_list.clear()
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


# ========================================================= Users extractor

def parse_user_tokens(text: str) -> list[str]:
    """Pulls usernames / numeric IDs out of a pasted list: one per line or
    comma/space separated; `@name`, `t.me/name` and plain names all work, and
    so do error-log lines like "! name: UserBlockedError: …" (only the part
    before the first colon counts). Returns lowercase usernames (no @) and
    numeric IDs as strings, de-duplicated, in order."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^[\s!*\-•]*@?[A-Za-z0-9_]+\s*:(?!//)", line)
        if m:
            line = line.split(":", 1)[0]
        for piece in re.split(r"[,\s]+", line):
            mm = re.match(r"^[!*\-•]*(?:https?://)?(?:t\.me/)?@?([A-Za-z0-9_]{3,})/?$",
                          piece.strip())
            if mm and mm.group(1).lower() not in out:
                out.append(mm.group(1).lower())
    return out


class _PasteEdit(QPlainTextEdit):
    """Emits `pasted` right after text is pasted into it."""
    pasted = Signal()

    def insertFromMimeData(self, source) -> None:  # noqa: N802 (Qt naming)
        super().insertFromMimeData(source)
        self.pasted.emit()


class UsersExtractorTab(ToolTab):
    tool_name = "users_extractor"

    def help_text(self) -> str:
        return self.tr_("users_extractor_help")

    def build_form(self) -> None:
        self._members_a: list[dict] = []
        self._members_b: list[dict] = []
        self._delta_members: list[dict] = []
        self._need_link: list[dict] = []  # couldn't be added directly
        self._excluded: set[str] = set()  # pasted: skip in direct add

        self.group_a_edit = QLineEdit(self.cfg.get("USERS_EXTRACTOR_GROUP_A"))
        a_row = QWidget()
        a_lay = QHBoxLayout(a_row)
        a_lay.setContentsMargins(0, 0, 0, 0)
        a_lay.addWidget(self.group_a_edit, stretch=1)
        self.add_result_label = QLabel("")  # who got added from A to B
        self.add_result_label.setStyleSheet("color: palette(placeholder-text);")
        a_lay.addWidget(self.add_result_label)
        self.form.addRow(self.tr_("users_extractor_group_a"), a_row)

        self.group_b_edit = QLineEdit(self.cfg.get("USERS_EXTRACTOR_GROUP_B"))
        b_row = QWidget()
        b_lay = QHBoxLayout(b_row)
        b_lay.setContentsMargins(0, 0, 0, 0)
        b_lay.addWidget(self.group_b_edit, stretch=1)
        self.add_all_btn = QPushButton()
        self.add_all_btn.clicked.connect(self._add_all_from_a)
        b_lay.addWidget(self.add_all_btn)
        self.add_link_btn = QPushButton()
        self.add_link_btn.clicked.connect(self._show_link_list)
        b_lay.addWidget(self.add_link_btn)
        self.form.addRow(self.tr_("users_extractor_group_b"), b_row)
        self._update_add_buttons()

        results_box = QWidget()
        results_lay = QVBoxLayout(results_box)
        results_lay.setContentsMargins(0, 0, 0, 0)

        algo_row = QHBoxLayout()
        algo_row.addWidget(QLabel(self.tr_("users_extractor_algo")))
        self.algo_combo = QComboBox()
        self.algo_combo.addItems([
            self.tr_("algo_a_only"), self.tr_("algo_b_only"),
            self.tr_("algo_intersection"), self.tr_("algo_symmetric_diff"),
        ])
        self.algo_combo.currentIndexChanged.connect(self._refresh_delta)
        algo_row.addWidget(self.algo_combo, stretch=1)
        save_html_btn = QPushButton(self.tr_("users_extractor_save_html"))
        save_html_btn.clicked.connect(self._save_html)
        algo_row.addWidget(save_html_btn)
        results_lay.addLayout(algo_row)

        tables_row = QHBoxLayout()
        self.table_a = QTableWidget(0, 2)
        self.table_b = QTableWidget(0, 2)
        self.table_delta = QTableWidget(0, 2)
        self._col_labels: dict[QTableWidget, tuple[QLabel, str]] = {}
        for table, title in (
            (self.table_a, self.tr_("users_extractor_col_a")),
            (self.table_b, self.tr_("users_extractor_col_b")),
            (self.table_delta, self.tr_("users_extractor_col_delta")),
        ):
            self._setup_user_table(table)
            col = QWidget()
            col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            col_lay = QVBoxLayout(col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            label = QLabel()
            col_lay.addWidget(label)
            col_lay.addWidget(table)
            self._col_labels[table] = (label, title)
            self._update_col_label(table)
            tables_row.addWidget(col, stretch=1)
        results_lay.addLayout(tables_row)

        # Added straight to the tab's root layout (with stretch) instead of
        # self.form.addRow(), so the tables actually grow when the window
        # is resized/maximized — a QFormLayout row only ever grows to its
        # widget's size hint.
        self.layout().addWidget(results_box, stretch=1)

    # ----------------------------------------------------------- user tables
    def _setup_user_table(self, table: QTableWidget) -> None:
        table.setHorizontalHeaderLabels([
            self.tr_("users_extractor_col_name"),
            self.tr_("users_extractor_col_username"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setMinimumHeight(220)
        table.setMinimumWidth(0)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_user_menu(t, pos))
        table.cellDoubleClicked.connect(
            lambda row, _col, t=table: self._open_user(t, row))

    def _update_col_label(self, table: QTableWidget) -> None:
        label, title = self._col_labels[table]
        label.setText(f"<b>{title} ({table.rowCount()})</b>")

    def _fill_table(self, table: QTableWidget, members: list[dict]) -> None:
        table.setRowCount(len(members))
        for row, m in enumerate(members):
            name_item = QTableWidgetItem(m["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, m)
            table.setItem(row, 0, name_item)
            table.setCellWidget(row, 1, self._make_username_cell(m))
        self._update_col_label(table)

    def _make_username_cell(self, m: dict) -> QWidget:
        text = f"@{m['username']}" if m.get("username") else f"#{m['id']}"
        cell = QWidget()
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.addWidget(QLabel(text), stretch=1)
        btn = QPushButton("📋")
        btn.setFixedWidth(24)
        btn.setToolTip(self.tr_("users_extractor_copy_username"))
        btn.clicked.connect(lambda _=False, mm=m: self._copy_username_or_link(mm))
        lay.addWidget(btn)
        return cell

    def _copy_username_or_link(self, m: dict) -> None:
        QApplication.clipboard().setText(m.get("username") or build_user_link(m))

    def _member_at(self, table: QTableWidget, row: int) -> dict | None:
        item = table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_user(self, table: QTableWidget, row: int) -> None:
        m = self._member_at(table, row)
        if m:
            QDesktopServices.openUrl(QUrl(build_user_link(m)))

    def _show_user_menu(self, table: QTableWidget, pos) -> None:
        row = table.rowAt(pos.y())
        m = self._member_at(table, row) if row >= 0 else None
        if not m:
            return
        menu = QMenu(self)
        copy_act = menu.addAction(self.tr_("users_extractor_copy_username"))
        open_act = menu.addAction(self.tr_("keep_open"))
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == copy_act:
            self._copy_username_or_link(m)
        elif chosen == open_act:
            QDesktopServices.openUrl(QUrl(build_user_link(m)))

    # ------------------------------------------------------------- delta
    def _refresh_delta(self) -> None:
        ids_a = {m["id"] for m in self._members_a}
        ids_b = {m["id"] for m in self._members_b}
        idx = self.algo_combo.currentIndex()
        if idx == 0:
            ids = ids_a - ids_b
        elif idx == 1:
            ids = ids_b - ids_a
        elif idx == 2:
            ids = ids_a & ids_b
        else:
            ids = ids_a ^ ids_b

        by_id = {m["id"]: m for m in self._members_b}
        by_id.update({m["id"]: m for m in self._members_a})
        self._delta_members = sorted((by_id[i] for i in ids),
                                     key=lambda m: m["name"].lower())
        self._fill_table(self.table_delta, self._delta_members)
        self._update_add_buttons()

    # --------------------------------------------------------- add A -> B
    def _a_only(self) -> list[dict]:
        ids_b = {m["id"] for m in self._members_b}
        # Bots can't be added to a group by a user account — skip them.
        return [m for m in self._members_a
                if m["id"] not in ids_b and not m.get("bot")
                and not self._user_keys(m) & self._excluded]

    @staticmethod
    def _user_keys(m: dict) -> set[str]:
        keys = {str(m["id"])} if m.get("id") is not None else set()
        if m.get("username"):
            keys.add(m["username"].lower())
        return keys

    def _update_add_buttons(self) -> None:
        n = len(self._a_only())
        self.add_all_btn.setText(self.tr_("users_extractor_add_all", n=n))
        self.add_all_btn.setEnabled(n > 0 and not self.is_running())
        self.add_link_btn.setText(
            self.tr_("users_extractor_add_link", n=len(self._need_link)))

    def set_extra_buttons_enabled(self, enabled: bool) -> None:
        if enabled:
            self._update_add_buttons()
        else:
            self.add_all_btn.setEnabled(False)

    def _add_all_from_a(self) -> None:
        if self.is_running() or not self.check_conn():
            return
        users = self._a_only()
        if not users or not self.group_b_edit.text().strip():
            return
        answer = QMessageBox.question(
            self, self.tr_("app_title"),
            self.tr_("users_extractor_add_confirm", n=len(users),
                     group=self.group_b_edit.text().strip()))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.add_result_label.setText("")
        self.launch(add_users_to_group,
                    {"group_b": self.group_b_edit.text().strip(), "users": users},
                    done_slot=self._on_add_done)

    def _on_add_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                data = json.loads(msg)
                added = data["added"]
                # Refused (privacy) and errored (blocked, too many channels,
                # bad ID…) users alike can only be reached with a link.
                have: set[str] = set()
                for m in self._need_link:
                    have |= self._user_keys(m)
                for m in data["need_link"] + data["failed"]:
                    if not self._user_keys(m) & have:
                        self._need_link.append(m)
                        have |= self._user_keys(m)
                    self._excluded |= self._user_keys(m)  # don't retry directly
                have = {m["id"] for m in self._members_b}
                self._members_b += [u for u in added if u["id"] not in have]
                self._fill_table(self.table_b, self._members_b)
                self._refresh_delta()
                self.add_result_label.setText(self.tr_(
                    "users_extractor_add_result", added=len(added),
                    link=len(self._need_link), failed=len(data["failed"])))
                msg = data["stopped_reason"] or self.tr_(
                    "users_extractor_add_done", added=len(added),
                    link=len(self._need_link))
            except (ValueError, KeyError):
                ok = False
        ToolTab.on_done(self, ok, msg)  # base reset; our on_done expects diff JSON

    def _show_link_list(self) -> None:
        dlg = QDialog(self)
        dlg.resize(500, 560)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(self.tr_("users_extractor_link_hint")))

        lst = QListWidget()
        lay.addWidget(lst, stretch=1)
        lst.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl(it.data(Qt.ItemDataRole.UserRole))))
        status = QLabel("")
        status.setStyleSheet("color: palette(placeholder-text);")

        def refill() -> None:
            lst.clear()
            for m in self._need_link:
                link = build_user_link(m)
                item = QListWidgetItem(f"{m['name']} — {link}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, link)
                lst.addItem(item)
            dlg.setWindowTitle(self.tr_("users_extractor_add_link",
                                        n=len(self._need_link)))

        def set_all(state) -> None:
            for i in range(lst.count()):
                lst.item(i).setCheckState(state)

        def checked_links() -> list[str]:
            return [lst.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(lst.count())
                    if lst.item(i).checkState() == Qt.CheckState.Checked]

        row = QHBoxLayout()
        all_btn = QPushButton(self.tr_("keep_select_all"))
        all_btn.clicked.connect(lambda: set_all(Qt.CheckState.Checked))
        none_btn = QPushButton(self.tr_("keep_select_none"))
        none_btn.clicked.connect(lambda: set_all(Qt.CheckState.Unchecked))
        copy_btn = QPushButton(self.tr_("users_extractor_copy_checked_links"))
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText("\n".join(checked_links())))
        for b in (all_btn, none_btn, copy_btn):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(QLabel(self.tr_("users_extractor_paste_label")))
        paste = _PasteEdit()
        paste.setPlaceholderText(self.tr_("users_extractor_paste_placeholder"))
        paste.setMaximumHeight(110)
        lay.addWidget(paste)
        lay.addWidget(status)

        def on_pasted() -> None:
            n = self._load_pasted_list(paste.toPlainText())
            paste.clear()
            status.setText(self.tr_("users_extractor_paste_loaded", n=n))
            refill()

        paste.pasted.connect(on_pasted)
        refill()
        dlg.exec()

    def _load_pasted_list(self, text: str) -> int:
        """A pasted list = people who must not be tried by a direct add and
        need a link instead. Matches them to Group A members where possible
        (name/ID); a username not in A still gets a t.me link of its own."""
        tokens = parse_user_tokens(text)
        have: set[str] = set()
        for m in self._need_link:
            have |= self._user_keys(m)
        by_key: dict[str, dict] = {}
        for m in self._members_a:
            for k in self._user_keys(m):
                by_key[k] = m
        for tok in tokens:
            self._excluded.add(tok)
            m = by_key.get(tok)
            if m is not None:
                self._excluded |= self._user_keys(m)
            elif tok.isdigit():
                continue  # unknown bare ID: no link can be built from it
            else:
                m = {"id": None, "username": tok, "name": f"@{tok}"}
            if m is not None and not self._user_keys(m) & have:
                self._need_link.append(m)
                have |= self._user_keys(m)
        self._update_add_buttons()
        return len(tokens)

    # -------------------------------------------------------------- export
    def _save_html(self) -> None:
        if not self._members_a and not self._members_b:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("users_extractor_nothing_to_save"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr_("users_extractor_save_html"), "users_diff.html",
            "HTML (*.html)")
        if not path:
            return
        html = render_users_html(self.tr_("tab_users_extractor"), [
            (self.tr_("users_extractor_col_a"), self._members_a),
            (self.tr_("users_extractor_col_b"), self._members_b),
            (f"{self.tr_('users_extractor_col_delta')} — {self.algo_combo.currentText()}",
             self._delta_members),
        ])
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except OSError as exc:
            QMessageBox.warning(self, self.tr_("app_title"), str(exc))
            return
        self.append_log(self.tr_("users_extractor_saved", path=path))

    # -------------------------------------------------------------- run
    def collect_params(self) -> dict | None:
        if not self.group_a_edit.text().strip() or not self.group_b_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("users_extractor_need_groups"))
            return None
        self.cfg.profile["USERS_EXTRACTOR_GROUP_A"] = self.group_a_edit.text().strip()
        self.cfg.profile["USERS_EXTRACTOR_GROUP_B"] = self.group_b_edit.text().strip()
        self.cfg.save()
        return {
            "group_a": self.group_a_edit.text().strip(),
            "group_b": self.group_b_edit.text().strip(),
        }

    def tool_func(self):
        return run_users_extractor

    def on_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                data = json.loads(msg)
                self._members_a = data["a"]["members"]
                self._members_b = data["b"]["members"]
                b_keys: set[str] = set()
                for m in self._members_b:
                    b_keys |= self._user_keys(m)
                self._need_link = [m for m in self._need_link
                                   if not self._user_keys(m) & b_keys]
                self.add_result_label.setText("")
                self._fill_table(self.table_a, self._members_a)
                self._fill_table(self.table_b, self._members_b)
                self._refresh_delta()
                msg = self.tr_("users_extractor_done",
                               a=len(self._members_a), b=len(self._members_b))
            except (ValueError, KeyError):
                ok = False
        super().on_done(ok, msg)


# ==================================================== Post image replacer

class PostImageReplacerTab(ToolTab):
    tool_name = "post_image_replacer"

    def help_text(self) -> str:
        return self.tr_("post_replacer_help")

    def build_form(self) -> None:
        self._rows: list[dict] = []

        self.channel_edit = QLineEdit(self.cfg.get("CHANNEL_ID"))
        self.form.addRow(self.tr_("post_replacer_channel"), self.channel_edit)

        self.posts_edit = QLineEdit()
        self.posts_edit.setPlaceholderText(self.tr_("post_replacer_posts_placeholder"))
        self.form.addRow(self.tr_("post_replacer_posts"), self.posts_edit)

        self.skip_edit = QLineEdit()
        self.skip_edit.setPlaceholderText(self.tr_("post_replacer_skip_placeholder"))
        self.form.addRow(self.tr_("post_replacer_skip"), self.skip_edit)

        load_btn = QPushButton(self.tr_("post_replacer_load"))
        load_btn.clicked.connect(self._load_rows)
        self.form.addRow("", load_btn)

        bulk_box = QWidget()
        bulk_lay = QHBoxLayout(bulk_box)
        bulk_lay.setContentsMargins(0, 0, 0, 0)
        self.bulk_image_edit = QLineEdit()
        self.bulk_image_edit.setPlaceholderText(self.tr_("post_replacer_keep_original"))
        bulk_lay.addWidget(_image_file_row(self, self.bulk_image_edit, self.tr_("browse")),
                           stretch=1)
        self.bulk_text_edit = QLineEdit()
        self.bulk_text_edit.setPlaceholderText(self.tr_("post_replacer_keep_original"))
        bulk_lay.addWidget(self.bulk_text_edit, stretch=1)
        apply_btn = QPushButton(self.tr_("post_replacer_apply_all"))
        apply_btn.clicked.connect(self._apply_bulk)
        bulk_lay.addWidget(apply_btn)
        self.form.addRow(self.tr_("post_replacer_bulk"), bulk_box)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            self.tr_("post_replacer_col_id"), self.tr_("post_replacer_col_link"),
            self.tr_("post_replacer_col_image"), self.tr_("post_replacer_col_text"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row_link)
        self.table.setMinimumHeight(220)
        self.form.addRow(self.tr_("post_replacer_table"), self.table)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 60.0); self.delay_spin.setValue(1.0)
        self.form.addRow(self.tr_("delay"), self.delay_spin)

    # ------------------------------------------------------------- rows
    def _load_rows(self) -> None:
        post_ids = parse_id_ranges(self.posts_edit.text())
        if not post_ids:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("post_replacer_no_posts"))
            return
        skip_ids = set(parse_id_ranges(self.skip_edit.text()))
        final_ids = [i for i in post_ids if i not in skip_ids]

        self.table.setRowCount(0)
        self._rows = []
        for pid in final_ids:
            self._add_row(pid)

    def _add_row(self, pid: int) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        id_item = QTableWidgetItem(str(pid))
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, id_item)

        link_item = QTableWidgetItem(build_post_link(self.channel_edit.text(), pid))
        link_item.setFlags(link_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 1, link_item)

        image_edit = QLineEdit()
        image_edit.setPlaceholderText(self.tr_("post_replacer_keep_original"))
        self.table.setCellWidget(row, 2, _image_file_row(self, image_edit, self.tr_("browse")))

        text_edit = QLineEdit()
        text_edit.setPlaceholderText(self.tr_("post_replacer_keep_original"))
        self.table.setCellWidget(row, 3, text_edit)

        self._rows.append({"id": pid, "image_edit": image_edit, "text_edit": text_edit})

    def _open_row_link(self, row: int, col: int) -> None:
        if col != 1:
            return
        item = self.table.item(row, 1)
        if item:
            QDesktopServices.openUrl(QUrl(item.text()))

    def _apply_bulk(self) -> None:
        image = self.bulk_image_edit.text().strip()
        text = self.bulk_text_edit.text()
        for r in self._rows:
            if image:
                r["image_edit"].setText(image)
            if text:
                r["text_edit"].setText(text)

    # -------------------------------------------------------------- run
    def collect_params(self) -> dict | None:
        if not self.channel_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("post_replacer_channel"))
            return None
        if not self._rows:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("post_replacer_no_rows"))
            return None

        mapping = []
        for r in self._rows:
            image = r["image_edit"].text().strip()
            text = r["text_edit"].text()
            if not image and not text.strip():
                continue
            if image and not os.path.isfile(image):
                QMessageBox.warning(self, self.tr_("app_title"),
                                    self.tr_("post_replacer_bad_image", path=image))
                return None
            mapping.append({
                "id": r["id"],
                "image": image or None,
                "text": text if text.strip() else None,
            })
        if not mapping:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("post_replacer_no_rows"))
            return None

        self.cfg.profile["CHANNEL_ID"] = self.channel_edit.text().strip()
        self.cfg.save()
        return {
            "channel": self.channel_edit.text().strip(),
            "mapping": mapping,
            "delay": self.delay_spin.value(),
        }

    def tool_func(self):
        return run_post_image_replace


# ============================================================ Links extract

class LinksCompareTab(ToolTab):
    tool_name = "links_compare"

    # column index -> row-dict key used for sorting
    _SORT_KEYS = {0: "followers", 1: "link", 2: "tag"}

    def __init__(self, cfg, i18n, parent=None) -> None:
        super().__init__(cfg, i18n, parent)
        # The results table is the point of this tab — cap the log so
        # window-height growth goes to the table instead of being split
        # 50/50 with it.
        self.log_view.setMaximumHeight(160)

    def help_text(self) -> str:
        return self.tr_("links_compare_help")

    def build_form(self) -> None:
        self._rows: list[dict] = []
        self._sort_col = 0            # default: sort by followers
        self._sort_desc = True

        self.channel_edit = QLineEdit(self.cfg.get("LINKS_COMPARE_CHANNEL"))
        self.form.addRow(self.tr_("links_compare_channel"), self.channel_edit)

        # Always starts empty (not persisted) — a "just this once" filter,
        # not something you'd usually want to carry over into the next scan.
        self.from_users_edit = QLineEdit()
        self.from_users_edit.setPlaceholderText(
            self.tr_("links_compare_from_users_placeholder"))
        self.form.addRow(self.tr_("links_compare_from_users"), self.from_users_edit)

        self._period_keys = ["1m", "3m", "6m", "1y", "all"]
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            self.tr_("period_1m"), self.tr_("period_3m"), self.tr_("period_6m"),
            self.tr_("period_1y"), self.tr_("period_all"),
        ])
        saved_period = self.cfg.get("LINKS_COMPARE_PERIOD")
        if saved_period in self._period_keys:
            self.period_combo.setCurrentIndex(self._period_keys.index(saved_period))
        self.form.addRow(self.tr_("links_compare_period"), self.period_combo)

        self.include_non_tg_check = QCheckBox(self.tr_("links_compare_include_non_tg"))
        self.include_non_tg_check.setChecked(
            self.cfg.get("LINKS_COMPARE_INCLUDE_NON_TG") == "1")
        self.form.addRow("", self.include_non_tg_check)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 30.0)
        self.delay_spin.setSingleStep(0.5)
        try:
            self.delay_spin.setValue(
                float(self.cfg.get("LINKS_COMPARE_DELAY") or 2.0))
        except ValueError:
            self.delay_spin.setValue(2.0)
        self.form.addRow(self.tr_("links_compare_delay"), self.delay_spin)

        self.min_followers_spin = QSpinBox()
        self.min_followers_spin.setRange(0, 100_000_000)
        try:
            self.min_followers_spin.setValue(
                int(self.cfg.get("LINKS_COMPARE_MIN_FOLLOWERS") or 0))
        except ValueError:
            pass
        self.form.addRow(self.tr_("links_compare_min_followers"), self.min_followers_spin)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            self.tr_("links_compare_col_followers"),
            self.tr_("links_compare_col_link"),
            self.tr_("links_compare_col_tag"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.table.setMinimumHeight(260)
        # Added to the tab root (not the form row) so it grows on resize.
        self.layout().addWidget(self.table, stretch=1)

    def extra_buttons(self, layout) -> None:
        self.load_md_btn = QPushButton(self.tr_("links_compare_load_md_button"))
        self.load_md_btn.clicked.connect(self._load_md)
        layout.addWidget(self.load_md_btn)

        self.populate_public_btn = QPushButton(
            self.tr_("links_compare_populate_public_button"))
        self.populate_public_btn.clicked.connect(self._populate_followers)
        layout.addWidget(self.populate_public_btn)

        self.populate_private_btn = QPushButton(
            self.tr_("links_compare_populate_private_button"))
        self.populate_private_btn.clicked.connect(self._populate_private_channels)
        layout.addWidget(self.populate_private_btn)

        self.save_md_btn = QPushButton(self.tr_("links_compare_save_md_button"))
        self.save_md_btn.clicked.connect(self._save_md)
        layout.addWidget(self.save_md_btn)

        self.exclude_md_btn = QPushButton(self.tr_("links_compare_exclude_md_button"))
        self.exclude_md_btn.clicked.connect(self._exclude_by_md)
        layout.addWidget(self.exclude_md_btn)

    def set_extra_buttons_enabled(self, enabled: bool) -> None:
        self.load_md_btn.setEnabled(enabled)
        self.exclude_md_btn.setEnabled(enabled)
        self.populate_public_btn.setEnabled(enabled)
        self.populate_private_btn.setEnabled(enabled)
        self.save_md_btn.setEnabled(enabled)

    @staticmethod
    def _link_url(link: str) -> str:
        """t.me links are stored without a protocol ("t.me/x"); external
        (non-Telegram) links keep their own full URL as-is."""
        return link if link.startswith(("http://", "https://")) else f"https://{link}"

    def _open_row(self, row: int, col: int) -> None:
        if col != 1:
            return
        item = self.table.item(row, 1)
        if item and item.text():
            QDesktopServices.openUrl(QUrl(self._link_url(item.text())))

    # ------------------------------------------------------------- sorting
    def _on_header_clicked(self, col: int) -> None:
        if col == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = (col == 0)  # followers: highest first by default
        self._rebuild_table()

    def _followers_sort_key(self, row: dict):
        """Broken links sink below unresolved ones, which sink below any
        resolved count — so a followers-sorted view still reads top-to-
        -bottom as "best -> unknown -> confirmed broken"."""
        if row.get("broken"):
            return -2
        followers = row.get("followers")
        return followers if followers is not None else -1

    def _sort_value(self, row: dict, col: int):
        if col == 0:
            return self._followers_sort_key(row)
        return (row.get(self._SORT_KEYS[col]) or "").lower()

    def _update_sort_indicator(self) -> None:
        order = (Qt.SortOrder.DescendingOrder if self._sort_desc
                 else Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(self._sort_col, order)

    def _followers_text(self, row: dict) -> str:
        if row.get("broken"):
            return "❌"
        followers = row.get("followers")
        return str(followers) if followers is not None else self.tr_("links_compare_na")

    def _rebuild_table(self) -> None:
        rows = sorted(self._rows, key=lambda r: self._sort_value(r, self._sort_col),
                      reverse=self._sort_desc)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(self._followers_text(r)))
            link_item = QTableWidgetItem(r.get("link", ""))
            link_item.setToolTip(self._link_url(r.get("link", "")))
            self.table.setItem(i, 1, link_item)
            self.table.setItem(i, 2, QTableWidgetItem(r.get("tag", "")))
        self._update_sort_indicator()

    # -------------------------------------------------------------- run
    def _current_period(self) -> str:
        return self._period_keys[self.period_combo.currentIndex()]

    def collect_params(self) -> dict | None:
        channel = self.channel_edit.text().strip()
        if not channel:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("links_compare_channel"))
            return None
        from_users = self.from_users_edit.text().strip()
        period = self._current_period()
        self.cfg.profile["LINKS_COMPARE_CHANNEL"] = channel
        self.cfg.profile["LINKS_COMPARE_PERIOD"] = period
        self.cfg.profile["LINKS_COMPARE_INCLUDE_NON_TG"] = (
            "1" if self.include_non_tg_check.isChecked() else "0")
        self.cfg.save()
        return {
            "channel": channel,
            "period": period,
            "from_users": from_users,
            "include_non_tg": self.include_non_tg_check.isChecked(),
        }

    def tool_func(self):
        return scan_channel_links

    def on_run(self) -> None:
        if self.is_running() or not self.check_conn():
            return
        params = self.collect_params()
        if params is None:
            return
        self._rows = []
        self._rebuild_table()
        self.launch(scan_channel_links, params, partial_slot=self._on_partial_rows)

    def _on_partial_rows(self, new_rows: list) -> None:
        """Populates the table live during a scan (`ctx.emit_rows(...)`),
        instead of only showing results once the whole run finishes."""
        existing = {r["link"] for r in self._rows}
        for r in new_rows:
            if r["link"] not in existing:
                self._rows.append(r)
                existing.add(r["link"])
        self._rebuild_table()

    def on_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                data = json.loads(msg)
                self._rows = data["rows"]  # authoritative final set, replaces the streamed rows
                self._sort_col, self._sort_desc = 0, True  # default: by followers
                self._rebuild_table()
                msg = self.tr_("links_compare_done", n=len(self._rows),
                               scanned=data.get("scanned_links", 0))
            except (ValueError, KeyError):
                ok = False
        super().on_done(ok, msg)

    # ------------------------------------------------------------- populate
    def _populate_params(self) -> dict:
        self.cfg.profile["LINKS_COMPARE_MIN_FOLLOWERS"] = str(self.min_followers_spin.value())
        self.cfg.profile["LINKS_COMPARE_DELAY"] = str(self.delay_spin.value())
        self.cfg.save()
        return {
            "rows": self._rows,
            "min_followers": self.min_followers_spin.value(),
            "delay": self.delay_spin.value(),
        }

    def _populate_followers(self) -> None:
        if self.is_running() or not self.check_conn():
            return
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_empty"))
            return
        if not any(r.get("kind") == "user" and r.get("followers") is None
                  and not r.get("broken") for r in self._rows):
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_nothing_to_populate"))
            return
        self.launch(populate_followers, self._populate_params(),
                   done_slot=self._on_populate_done)

    def _populate_private_channels(self) -> None:
        if self.is_running() or not self.check_conn():
            return
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_empty"))
            return
        if not any(r.get("kind") == "invite" and r.get("followers") is None
                  and not r.get("broken") for r in self._rows):
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_nothing_to_populate"))
            return
        self.launch(populate_private_channels, self._populate_params(),
                   done_slot=self._on_populate_done)

    def _on_populate_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                data = json.loads(msg)
                self._rows = data["rows"]
                self._rebuild_table()
                if data.get("stopped_reason"):
                    msg = self.tr_("links_compare_populate_stopped",
                                   resolved=data.get("resolved", 0),
                                   dropped=data.get("dropped", 0),
                                   reason=data["stopped_reason"])
                else:
                    msg = self.tr_("links_compare_populate_done",
                                   resolved=data.get("resolved", 0),
                                   dropped=data.get("dropped", 0))
            except (ValueError, KeyError):
                ok = False
        ToolTab.on_done(self, ok, msg)  # base reset; our on_done expects scan JSON

    # ------------------------------------------------------------- load md
    def _load_md(self) -> None:
        if self.is_running():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr_("links_compare_load_md_button"), "", "Markdown (*.md)")
        if not path:
            return
        rows = parse_loadable_rows(path)
        if not rows:
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("links_compare_load_md_empty"))
            return
        self._rows = rows
        self._sort_col, self._sort_desc = 0, True  # default: by followers
        self._rebuild_table()
        self.append_log(self.tr_("links_compare_md_loaded", n=len(rows), path=path))

    # ---------------------------------------------------------- exclude md
    def _exclude_by_md(self) -> None:
        if self.is_running():
            return
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_empty"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr_("links_compare_exclude_md_button"), "", MD_FILTER)
        if not path:
            return
        self._rows, removed = exclude_by_md(self._rows, path)
        self._rebuild_table()
        self.append_log(self.tr_("links_compare_excluded", n=removed, path=path))

    # ------------------------------------------------------------- save md
    def _save_md(self) -> None:
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("links_compare_empty"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr_("links_compare_save_md_button"), "new_links.md",
            "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_md_table())
        except OSError as exc:
            QMessageBox.warning(self, self.tr_("app_title"), str(exc))
            return
        self.append_log(self.tr_("links_compare_md_saved", path=path))

    def _build_md_table(self) -> str:
        lines = ["|Followers|t.me/ link|tag|", "|---|---|---|"]
        rows = sorted(self._rows, key=self._followers_sort_key, reverse=True)
        for r in rows:
            if r.get("broken"):
                followers_text = "❌"
            else:
                followers = r.get("followers")
                followers_text = str(followers) if followers is not None else ""
            link = (r.get("link") or "").replace("|", "\\|")
            tag = (r.get("tag") or "").replace("|", "\\|").replace("\n", " ").strip()
            lines.append(f"|{followers_text}|{link}|{tag}|")
        return "\n".join(lines) + "\n"


# ============================================================ Chat activity

class ChatActivityTab(QWidget):
    """Analyzes a local Telegram Desktop chat export (result.json) for
    sender activity. Deliberately *not* a ToolTab — this needs no Telegram
    connection at all, so it gets its own minimal Run/Stop/log/progress
    wiring around `LocalTaskWorker` instead of the login-first machinery
    every other tab shares."""

    def __init__(self, cfg, i18n, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.i18n = i18n
        self.worker: LocalTaskWorker | None = None
        self._summary: dict | None = None

        root = QVBoxLayout(self)

        help_label = QLabel(self.tr_("chat_activity_help"))
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: palette(placeholder-text);")
        root.addWidget(help_label)

        form = QFormLayout()
        root.addLayout(form)

        self.path_edit = QLineEdit(self.cfg.get("CHAT_ACTIVITY_JSON_PATH"))
        form.addRow(self.tr_("chat_activity_json_path"),
                   _open_file_row(self, self.path_edit, self.tr_("browse"), JSON_FILTER))

        buttons = QHBoxLayout()
        self.run_btn = QPushButton(self.tr_("chat_activity_generate_button"))
        self.run_btn.clicked.connect(self._generate)
        buttons.addWidget(self.run_btn)
        self.stop_btn = QPushButton(self.tr_("stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        buttons.addWidget(self.stop_btn)
        self.save_md_btn = QPushButton(self.tr_("chat_activity_save_md_button"))
        self.save_md_btn.setEnabled(False)
        self.save_md_btn.clicked.connect(self._save_md)
        buttons.addWidget(self.save_md_btn)
        buttons.addStretch()
        root.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)

        root.addWidget(QLabel(self.tr_("log")))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMaximumHeight(120)
        root.addWidget(self.log_view)

        root.addWidget(QLabel(self.tr_("chat_activity_report_preview")))
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        root.addWidget(self.report_view, stretch=1)

    def tr_(self, key: str, **kw) -> str:
        return self.i18n.tr(key, **kw)

    # -------------------------------------------------------------- run
    def is_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _generate(self) -> None:
        if self.is_running():
            return
        path = self.path_edit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("chat_activity_bad_path"))
            return
        self.cfg.profile["CHAT_ACTIVITY_JSON_PATH"] = path
        self.cfg.save()

        self.report_view.clear()
        self.log_view.clear()
        self.save_md_btn.setEnabled(False)
        self.worker = LocalTaskWorker(run_chat_activity, {"path": path}, parent=self)
        self.worker.sig_log.connect(self._append_log)
        self.worker.sig_progress.connect(self._on_progress)
        self.worker.sig_done.connect(self._on_done)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setRange(0, 0)  # busy until the first progress signal
        self.worker.start()

    def _stop(self) -> None:
        if self.worker:
            self._append_log(self.tr_("cancelled"))
            self.worker.request_cancel()
            self.stop_btn.setEnabled(False)

    def _append_log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)

    def _on_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                self._summary = json.loads(msg)
                self.report_view.setPlainText(self._build_report_md())
                self.save_md_btn.setEnabled(True)
                msg = self.tr_("chat_activity_done",
                               senders=self._summary["total_senders"],
                               one=len(self._summary["one_message_users"]))
            except (ValueError, KeyError):
                ok = False
        self._append_log(self.tr_("done_ok" if ok else "done_fail", msg=msg))
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if ok else 0)
        self.worker = None

    # ------------------------------------------------------------- report
    def _build_report_md(self) -> str:
        """Plain, unlocalized English structure — matches how every other
        exported .md in this app is built, independent of the UI language."""
        s = self._summary
        lines = [f"# Chat Activity Report — {s['chat_name']}", ""]
        lines.append(f"Total entries: {s['total_entries']} · "
                     f"Authored messages: {s['total_authored']} · "
                     f"Unique senders: {s['total_senders']}")
        lines.append("")
        lines.append("## Active senders by period")
        lines.append("")
        lines.append("| Period | Active users |")
        lines.append("|---|---|")
        for key, label, _days in PERIODS:
            lines.append(f"| {label} | {s['active_by_period'][key]} |")
        lines.append("")
        one = s["one_message_users"]
        lines.append(f"## Users with exactly 1 message — {len(one)}")
        lines.append("")
        lines.append("| Name | ID |")
        lines.append("|---|---|")
        for u in one:
            name = (u.get("name") or "").replace("|", "\\|")
            lines.append(f"| {name} | {u['id']} |")
        return "\n".join(lines) + "\n"

    def _save_md(self) -> None:
        if not self._summary:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr_("chat_activity_save_md_button"), "chat_activity.md",
            "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_report_md())
        except OSError as exc:
            QMessageBox.warning(self, self.tr_("app_title"), str(exc))
            return
        self._append_log(self.tr_("chat_activity_md_saved", path=path))

