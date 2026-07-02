"""Config tab: profile management + connection/channel fields + instructions."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..config import CONN_FIELDS


class ConfigTab(QWidget):
    profile_changed = Signal()  # other tabs may want to refresh defaults

    def __init__(self, cfg, i18n, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.i18n = i18n
        tr = i18n.tr

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)

        # ------------------------------------------------------- profiles
        prow = QHBoxLayout()
        prow.addWidget(QLabel(tr("profile")))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(sorted(self.cfg.profiles))
        self.profile_combo.setCurrentText(self.cfg.current_profile)
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        prow.addWidget(self.profile_combo, stretch=1)

        new_btn = QPushButton(tr("new_profile"))
        new_btn.clicked.connect(self._new_profile)
        prow.addWidget(new_btn)
        del_btn = QPushButton(tr("delete_profile"))
        del_btn.clicked.connect(self._delete_profile)
        prow.addWidget(del_btn)
        root.addLayout(prow)

        # -------------------------------------------------------- fields
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for key in CONN_FIELDS:
            edit = QLineEdit()
            if key == "API_HASH":
                edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
            self.edits[key] = edit
            form.addRow(tr(f"field_{key}"), edit)
        root.addLayout(form)

        # ------------------------------------------------------- buttons
        brow = QHBoxLayout()
        save_btn = QPushButton(tr("save"))
        save_btn.clicked.connect(self._save)
        brow.addWidget(save_btn)
        imp_btn = QPushButton(tr("import_env"))
        imp_btn.clicked.connect(self._import_env)
        brow.addWidget(imp_btn)
        exp_btn = QPushButton(tr("export_env"))
        exp_btn.clicked.connect(self._export_env)
        brow.addWidget(exp_btn)
        brow.addStretch()
        root.addLayout(brow)

        self.status = QLabel("")
        root.addWidget(self.status)

        # -------------------------------------------------- instructions
        box = QGroupBox(tr("instructions_title"))
        box.setCheckable(True)
        box.setChecked(True)
        box_lay = QVBoxLayout(box)
        info = QLabel(tr("instructions_text"))
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        box_lay.addWidget(info)
        box.toggled.connect(info.setVisible)
        root.addWidget(box)

        loc = QLabel(tr("config_location", path=str(self.cfg.path)))
        loc.setStyleSheet("color: palette(mid);")
        loc.setWordWrap(True)
        root.addWidget(loc)
        root.addStretch()

        self._load_fields()

    # ----------------------------------------------------------- helpers
    def _load_fields(self) -> None:
        for key, edit in self.edits.items():
            edit.setText(self.cfg.get(key))

    def _store_fields(self) -> None:
        for key, edit in self.edits.items():
            self.cfg.profile[key] = edit.text().strip()

    def _save(self) -> None:
        self._store_fields()
        self.cfg.save()
        self.status.setText(self.i18n.tr("saved"))
        self.profile_changed.emit()

    # ---------------------------------------------------------- profiles
    def _switch_profile(self, name: str) -> None:
        if not name or name == self.cfg.current_profile:
            return
        self._store_fields()          # keep edits of the profile we leave
        self.cfg.current_profile = name
        self.cfg.save()
        self._load_fields()
        self.profile_changed.emit()

    def _new_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, self.i18n.tr("new_profile"), self.i18n.tr("profile_name"))
        if not ok:
            return
        self._store_fields()
        if self.cfg.add_profile(name):
            self.cfg.save()
            self.profile_combo.blockSignals(True)
            self.profile_combo.addItem(name.strip())
            self.profile_combo.setCurrentText(name.strip())
            self.profile_combo.blockSignals(False)
            self._load_fields()
            self.profile_changed.emit()

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentText()
        answer = QMessageBox.question(
            self, self.i18n.tr("delete_profile"),
            self.i18n.tr("delete_profile_confirm", name=name))
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.cfg.delete_profile(name):
            self.cfg.save()
            self.profile_combo.blockSignals(True)
            self.profile_combo.removeItem(self.profile_combo.currentIndex())
            self.profile_combo.setCurrentText(self.cfg.current_profile)
            self.profile_combo.blockSignals(False)
            self._load_fields()
            self.profile_changed.emit()

    # ------------------------------------------------------------ env io
    def _import_env(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.i18n.tr("import_env"), "", "env (*.env *.*)")
        if not path:
            return
        n = self.cfg.import_env(path)
        self._load_fields()
        self.cfg.save()
        self.status.setText(self.i18n.tr("env_imported", n=n))
        self.profile_changed.emit()

    def _export_env(self) -> None:
        self._store_fields()
        path, _ = QFileDialog.getSaveFileName(
            self, self.i18n.tr("export_env"), ".env", "env (*.env *.*)")
        if not path:
            return
        self.cfg.export_env(path)
        self.status.setText(path)
