"""Concrete tool tabs."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSizePolicy,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..tools.backup import run_backup
from ..tools.channel_top import count_posts_in_period, run_channel_top
from ..tools.cleaner import run_cleaner, scan_keep_candidates
from ..tools.common import reset_progress
from ..tools.post_image_replacer import run_post_image_replace
from ..tools.repost import run_repost
from ..tools.repost_group import count_repost_group, run_repost_group
from ..tools.restore import run_restore
from ..tools.users_extractor import run_users_extractor
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

class UsersExtractorTab(ToolTab):
    tool_name = "users_extractor"

    def help_text(self) -> str:
        return self.tr_("users_extractor_help")

    def build_form(self) -> None:
        self.group_a_edit = QLineEdit(self.cfg.get("USERS_EXTRACTOR_GROUP_A"))
        self.form.addRow(self.tr_("users_extractor_group_a"), self.group_a_edit)

        self.group_b_edit = QLineEdit(self.cfg.get("USERS_EXTRACTOR_GROUP_B"))
        self.form.addRow(self.tr_("users_extractor_group_b"), self.group_b_edit)

        self._members_a: list[dict] = []
        self._members_b: list[dict] = []
        self._delta_members: list[dict] = []

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


# ===================================================== Public reposts dialog

class PublicForwardsDialog(QDialog):
    """Lists the public channels that forwarded one post — title, views and a
    clickable t.me link (double-click a row to open it)."""

    def __init__(self, parent, i18n, msg_id: int, items: list[dict]) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.setWindowTitle(i18n.tr("channel_top_public_title", id=msg_id))
        self.resize(560, 360)

        root = QVBoxLayout(self)
        if not items:
            root.addWidget(QLabel(i18n.tr("channel_top_public_empty")))
        else:
            self.table = QTableWidget(len(items), 3)
            self.table.setHorizontalHeaderLabels([
                i18n.tr("channel_top_public_col_channel"),
                i18n.tr("channel_top_public_col_views"),
                i18n.tr("channel_top_public_col_link"),
            ])
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.Stretch)
            self.table.cellDoubleClicked.connect(self._open_row)
            for row, it in enumerate(items):
                self.table.setItem(row, 0, QTableWidgetItem(it.get("title", "")))
                self.table.setItem(row, 1, QTableWidgetItem(str(it.get("views", 0))))
                link_item = QTableWidgetItem(it.get("link", ""))
                link_item.setToolTip(it.get("link", ""))
                self.table.setItem(row, 2, link_item)
            root.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _open_row(self, row: int, _col: int) -> None:
        item = self.table.item(row, 2)
        if item and item.text():
            QDesktopServices.openUrl(QUrl(item.text()))


# ======================================================= Channel top report

class ChannelReportDialog(QDialog):
    """Plain-text analytics summary — top posts by private reposts, views
    and reactions — read-only, for copying elsewhere (Telegram message,
    email, doc, …)."""

    def __init__(self, parent, i18n, text: str) -> None:
        super().__init__(parent)
        self._text = text
        self.setWindowTitle(i18n.tr("channel_top_report_dialog_title"))
        self.resize(640, 480)

        root = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        root.addWidget(view)

        row = QHBoxLayout()
        copy_btn = QPushButton(i18n.tr("channel_top_report_copy"))
        copy_btn.clicked.connect(self._copy)
        row.addWidget(copy_btn)
        row.addStretch()
        root.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._text)


# ============================================================= Channel top

class ChannelTopTab(ToolTab):
    tool_name = "channel_top"

    # column index -> row-dict key used for sorting (None = not sortable)
    _SORT_KEYS = {0: "ts", 2: "views", 3: "reactions", 4: "forwards", 5: "public"}

    def __init__(self, cfg, i18n, parent=None) -> None:
        super().__init__(cfg, i18n, parent)
        # The results table is the point of this tab, unlike the log-centric
        # tools — cap the log so window-height growth goes to the table
        # instead of being split 50/50 with it.
        self.log_view.setMaximumHeight(160)

    def help_text(self) -> str:
        return self.tr_("channel_top_help")

    def build_form(self) -> None:
        self._rows: list[dict] = []
        self._title = ""
        self._sort_col = 2          # default: sort by views
        self._sort_desc = True

        self.channel_edit = QLineEdit(self.cfg.get("CHANNEL_ID"))
        self.form.addRow(self.tr_("channel_top_channel"), self.channel_edit)

        self.top_spin = QSpinBox()
        self.top_spin.setRange(1, 1000)
        self.top_spin.setValue(20)
        self.form.addRow(self.tr_("channel_top_n"), self.top_spin)

        self._period_keys = ["3m", "6m", "1y", "2y", "3y", "all"]
        period_row = QWidget()
        period_lay = QHBoxLayout(period_row)
        period_lay.setContentsMargins(0, 0, 0, 0)
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            self.tr_("period_3m"), self.tr_("period_6m"), self.tr_("period_1y"),
            self.tr_("period_2y"), self.tr_("period_3y"), self.tr_("period_all"),
        ])
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        period_lay.addWidget(self.period_combo, stretch=1)
        self.period_count_label = QLabel("")
        self.period_count_label.setStyleSheet("color: palette(placeholder-text);")
        period_lay.addWidget(self.period_count_label)
        refresh_btn = QPushButton(" 🔄 ")
        refresh_btn.setToolTip(self.tr_("channel_top_period_refresh"))
        refresh_btn.clicked.connect(self._count_period)
        period_lay.addWidget(refresh_btn)
        self.form.addRow(self.tr_("channel_top_period"), period_row)
        self.channel_edit.textChanged.connect(
            lambda _=None: self.period_count_label.setText(""))
        self.channel_edit.editingFinished.connect(self._count_period)

        self.public_check = QCheckBox(self.tr_("channel_top_fetch_public"))
        self.form.addRow("", self.public_check)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            self.tr_("channel_top_col_date"), self.tr_("channel_top_col_post"),
            self.tr_("channel_top_col_views"), self.tr_("channel_top_col_reactions"),
            self.tr_("channel_top_col_private"), self.tr_("channel_top_col_public"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.table.setMinimumHeight(260)
        # Added to the tab root (not the form row) so it grows on resize.
        self.layout().addWidget(self.table, stretch=1)

    def extra_buttons(self, layout) -> None:
        self.report_btn = QPushButton(self.tr_("channel_top_report_button"))
        self.report_btn.clicked.connect(self._show_report)
        layout.addWidget(self.report_btn)

        self.save_md_btn = QPushButton(self.tr_("channel_top_save_md_button"))
        self.save_md_btn.clicked.connect(self._save_md)
        layout.addWidget(self.save_md_btn)

    def set_extra_buttons_enabled(self, enabled: bool) -> None:
        self.report_btn.setEnabled(enabled)
        self.save_md_btn.setEnabled(enabled)

    # -------------------------------------------------------------- period
    def _current_period(self) -> str:
        return self._period_keys[self.period_combo.currentIndex()]

    def _has_conn(self) -> bool:
        return bool(self.cfg.get("API_ID").strip() and self.cfg.get("API_HASH").strip()
                   and self.cfg.get("PHONE_NUMBER").strip())

    def _on_period_changed(self, _index: int = 0) -> None:
        self._count_period()

    def _count_period(self) -> None:
        channel = self.channel_edit.text().strip()
        if not channel or self.is_running() or not self._has_conn():
            return
        self.period_count_label.setText(self.tr_("channel_top_counting"))
        self.launch(count_posts_in_period,
                   {"channel": channel, "period": self._current_period()},
                   done_slot=self._on_period_count_done)

    def _on_period_count_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                n = json.loads(msg)["count"]
            except (ValueError, KeyError):
                ok = False
            else:
                msg = self.tr_("channel_top_period_count", n=n)
                self.period_count_label.setText(msg)
        if not ok:
            self.period_count_label.setText("")
        ToolTab.on_done(self, ok, msg)  # base reset; our on_done expects scan JSON

    # ------------------------------------------------------------- sorting
    def _on_header_clicked(self, col: int) -> None:
        if self._SORT_KEYS.get(col) is None:
            return
        if col == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = True
        self._rebuild_table()

    def _sort_value(self, row: dict, col: int):
        if col == 5:  # public reposts: unfetched / unavailable sort lowest
            pub = row.get("public")
            return pub["count"] if pub and pub["count"] >= 0 else -1
        return row.get(self._SORT_KEYS[col], 0)

    def _rebuild_table(self) -> None:
        rows = sorted(self._rows, key=lambda r: self._sort_value(r, self._sort_col),
                      reverse=self._sort_desc)
        channel = self.channel_edit.text()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            link = build_post_link(channel, r["id"])

            date_item = QTableWidgetItem(self._fmt_date(r.get("date", "")))
            self.table.setItem(i, 0, date_item)

            post_text = r.get("text", "") or f"#{r['id']}"
            album_ids = r.get("ids") or [r["id"]]
            if len(album_ids) > 1:
                post_text += self.tr_("channel_top_album_suffix", n=len(album_ids))
            post_item = QTableWidgetItem(post_text)
            post_item.setToolTip(link)
            post_item.setData(Qt.ItemDataRole.UserRole, link)
            self.table.setItem(i, 1, post_item)

            self.table.setItem(i, 2, QTableWidgetItem(str(r.get("views", 0))))
            self.table.setItem(i, 3, QTableWidgetItem(str(r.get("reactions", 0))))
            self.table.setItem(i, 4, QTableWidgetItem(str(r.get("forwards", 0))))
            self.table.setCellWidget(i, 5, self._public_cell(r))
        self._update_sort_indicator()

    def _update_sort_indicator(self) -> None:
        order = (Qt.SortOrder.DescendingOrder if self._sort_desc
                 else Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(self._sort_col, order)

    def _fmt_date(self, iso: str) -> str:
        if not iso:
            return ""
        try:
            return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d")
        except ValueError:
            return iso

    def _fmt_datetime(self, iso: str) -> str:
        if not iso:
            return ""
        try:
            return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return iso

    def _public_cell(self, row: dict) -> QWidget:
        cell = QWidget()
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(4, 0, 4, 0)
        pub = row.get("public")
        if pub is None:
            lay.addWidget(QLabel(self.tr_("channel_top_public_off")))
        elif pub["count"] < 0:
            lay.addWidget(QLabel(self.tr_("channel_top_public_na")))
        else:
            lay.addWidget(QLabel(str(pub["count"])), stretch=1)
            if pub["count"] > 0:
                btn = QPushButton(self.tr_("channel_top_show"))
                btn.clicked.connect(
                    lambda _=False, r=row: self._show_public(r))
                lay.addWidget(btn)
        return cell

    def _show_public(self, row: dict) -> None:
        pub = row.get("public") or {"items": []}
        PublicForwardsDialog(self, self.i18n, row["id"], pub.get("items", [])).exec()

    def _open_row(self, row: int, _col: int) -> None:
        item = self.table.item(row, 1)
        if item:
            link = item.data(Qt.ItemDataRole.UserRole)
            if link:
                QDesktopServices.openUrl(QUrl(link))

    # -------------------------------------------------------------- run
    def collect_params(self) -> dict | None:
        if not self.channel_edit.text().strip():
            QMessageBox.warning(self, self.tr_("app_title"),
                                self.tr_("channel_top_channel"))
            return None
        self.cfg.profile["CHANNEL_ID"] = self.channel_edit.text().strip()
        self.cfg.save()
        return {
            "channel": self.channel_edit.text().strip(),
            "top_n": self.top_spin.value(),
            "period": self._current_period(),
            "fetch_public": self.public_check.isChecked(),
        }

    def tool_func(self):
        return run_channel_top

    def on_done(self, ok: bool, msg: str) -> None:
        if ok:
            try:
                data = json.loads(msg)
                self._rows = data["rows"]
                self._title = data.get("title", "")
                self._sort_col, self._sort_desc = 2, True
                self._rebuild_table()
                msg = self.tr_("channel_top_done",
                               n=len(self._rows), scanned=data.get("scanned", 0))
            except (ValueError, KeyError):
                ok = False
        super().on_done(ok, msg)

    # ------------------------------------------------------------- report
    def _show_report(self) -> None:
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("channel_top_report_empty"))
            return
        ChannelReportDialog(self, self.i18n, self._build_report_text()).exec()

    def _build_report_text(self) -> str:
        channel_text = self.channel_edit.text().strip()
        title = self._title or channel_text
        lines = [self.tr_("channel_top_report_title", title=title), ""]
        for key, header_key, emoji in (
            ("forwards", "channel_top_report_private", "🔄"),
            ("views", "channel_top_report_views", "👁"),
            ("reactions", "channel_top_report_reactions", "❤️"),
        ):
            lines.append(self.tr_(header_key, emoji=emoji))
            lines.append("")
            top = sorted(self._rows, key=lambda r: r.get(key, 0), reverse=True)[:7]
            for i, r in enumerate(top, 1):
                link = build_post_link(channel_text, r["id"])
                link = link.removeprefix("https://").removeprefix("http://")
                snippet = (r.get("text") or "").strip()
                if len(snippet) > 50:
                    snippet = snippet[:49] + "…"
                if not snippet:
                    snippet = f"#{r['id']}"
                lines.append(f"{i}. {r.get(key, 0)} {emoji} {link} {snippet}")
            lines.append("")
            lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"

    # ------------------------------------------------------------- save md
    def _public_text(self, row: dict) -> str:
        """Plain count for the on-screen cell label (see _public_cell)."""
        pub = row.get("public")
        if pub is None:
            return self.tr_("channel_top_public_off")
        if pub["count"] < 0:
            return self.tr_("channel_top_public_na")
        return str(pub["count"])

    def _public_md(self, row: dict) -> str:
        """Count plus a link per public repost, for the Markdown table cell —
        each `[channel title](link)`, stacked with <br> inside the cell."""
        pub = row.get("public")
        if pub is None:
            return self.tr_("channel_top_public_off")
        if pub["count"] < 0:
            return self.tr_("channel_top_public_na")
        items = pub.get("items") or []
        if not items:
            return str(pub["count"])
        links = []
        for it in items:
            title = " ".join((it.get("title") or "?").split())
            title = title.replace("|", "\\|").replace("[", "(").replace("]", ")")
            link = it.get("link") or ""
            links.append(f"[{title}]({link})" if link else title)
        return f"{pub['count']} " + "<br>".join(links)

    def _save_md(self) -> None:
        if not self._rows:
            QMessageBox.information(self, self.tr_("app_title"),
                                    self.tr_("channel_top_report_empty"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr_("channel_top_save_md_button"), "channel_top.md",
            "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_md_table())
        except OSError as exc:
            QMessageBox.warning(self, self.tr_("app_title"), str(exc))
            return
        self.append_log(self.tr_("channel_top_md_saved", path=path))

    def _build_md_table(self) -> str:
        channel_text = self.channel_edit.text().strip()
        title = self._title or channel_text
        rows = sorted(self._rows, key=lambda r: self._sort_value(r, self._sort_col),
                      reverse=self._sort_desc)

        lines = [f"# {self.tr_('channel_top_report_title', title=title)}", ""]
        headers = [
            self.tr_("channel_top_col_date"), self.tr_("channel_top_col_post"),
            self.tr_("channel_top_col_views"), self.tr_("channel_top_col_reactions"),
            self.tr_("channel_top_col_private"), self.tr_("channel_top_col_public"),
        ]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for r in rows:
            link = build_post_link(channel_text, r["id"])
            text = (r.get("full_text") or r.get("text") or f"#{r['id']}")
            text = text.replace("|", "\\|").replace("\n", " ").strip() or f"#{r['id']}"
            date = self._fmt_datetime(r.get("date", ""))
            lines.append(
                f"| {date} | [{text}]({link}) | {r.get('views', 0)} | "
                f"{r.get('reactions', 0)} | {r.get('forwards', 0)} | "
                f"{self._public_md(r)} |"
            )
        return "\n".join(lines) + "\n"
