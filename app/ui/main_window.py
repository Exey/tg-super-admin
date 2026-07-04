"""Main window: 5 tabs, File / Language menus, Ctrl+1..5 tab shortcuts."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from ..config import Config, config_dir
from ..i18n import I18n
from .config_tab import ConfigTab
from .tool_tabs import (
    BackupTab, CleanerTab, RepostGroupTab, RepostTab, RestoreTab,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config()
        self.i18n = I18n(self.cfg.language)
        self.resize(860, 680)
        self._build_ui()

    # ------------------------------------------------------------ UI build
    def _build_ui(self) -> None:
        tr = self.i18n.tr
        self.setWindowTitle(tr("app_title"))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = ConfigTab(self.cfg, self.i18n)
        self.backup_tab = BackupTab(self.cfg, self.i18n)
        self.restore_tab = RestoreTab(self.cfg, self.i18n)
        self.repost_tab = RepostTab(self.cfg, self.i18n)
        self.repost_group_tab = RepostGroupTab(self.cfg, self.i18n)
        self.cleaner_tab = CleanerTab(self.cfg, self.i18n)

        self.tool_tabs = [self.backup_tab, self.restore_tab, self.repost_tab,
                          self.repost_group_tab, self.cleaner_tab]

        self.tabs.addTab(self.config_tab, tr("tab_config"))
        self.tabs.addTab(self.backup_tab, tr("tab_backup"))
        self.tabs.addTab(self.restore_tab, tr("tab_restore"))
        self.tabs.addTab(self.repost_tab, tr("tab_repost"))
        self.tabs.addTab(self.repost_group_tab, tr("tab_repost_group"))
        self.tabs.addTab(self.cleaner_tab, tr("tab_cleaner"))

        self.config_tab.profile_changed.connect(self._refresh_tab_defaults)

        self._build_menu()
        self._build_shortcuts()

    def _build_menu(self) -> None:
        tr = self.i18n.tr
        self.menuBar().clear()

        file_menu = self.menuBar().addMenu(tr("menu_file"))

        imp = QAction(tr("import_env"), self)
        imp.triggered.connect(self.config_tab._import_env)
        file_menu.addAction(imp)

        exp = QAction(tr("export_env"), self)
        exp.triggered.connect(self.config_tab._export_env)
        file_menu.addAction(exp)

        file_menu.addSeparator()
        open_cfg = QAction(tr("open_config_folder"), self)
        open_cfg.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(config_dir()))))
        file_menu.addAction(open_cfg)

        file_menu.addSeparator()
        quit_act = QAction(tr("quit"), self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        lang_menu = self.menuBar().addMenu(tr("menu_language"))
        for code, label_key in (("en", "lang_en"), ("ru", "lang_ru")):
            act = QAction(tr(label_key), self)
            act.setCheckable(True)
            act.setChecked(self.i18n.lang == code)
            act.triggered.connect(
                lambda _=False, c=code: self._switch_language(c))
            lang_menu.addAction(act)

    def _build_shortcuts(self) -> None:
        # Ctrl+1 … Ctrl+5 jump straight to a tab.
        for i in range(self.tabs.count()):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

    # ------------------------------------------------------------- actions
    def _any_worker_running(self) -> bool:
        return any(tab.is_running() for tab in self.tool_tabs)

    def _switch_language(self, code: str) -> None:
        if code == self.i18n.lang:
            self._build_menu()  # restore the check mark
            return
        if self._any_worker_running():
            QMessageBox.warning(self, self.i18n.tr("app_title"),
                                self.i18n.tr("worker_running"))
            self._build_menu()
            return
        self.i18n.lang = code
        self.cfg.language = code
        self.cfg.save()
        current = self.tabs.currentIndex()
        self._build_ui()  # rebuild everything with the new language
        QTimer.singleShot(0, lambda: self.tabs.setCurrentIndex(current))

    def _refresh_tab_defaults(self) -> None:
        """Push new profile values into tool tab fields (only if idle)."""
        if self._any_worker_running():
            return
        self.backup_tab.group_edit.setText(self.cfg.get("CHANNEL_ID"))
        self.restore_tab.chat_edit.setText(self.cfg.get("CHAT_ID"))
        try:
            self.restore_tab.topic_spin.setValue(
                int(self.cfg.get("TOPIC_ID") or 0))
        except ValueError:
            self.restore_tab.topic_spin.setValue(0)
        self.repost_tab.source_edit.setText(self.cfg.get("SOURCE_CHANNEL"))
        self.repost_tab.target_edit.setText(self.cfg.get("TARGET_CHANNEL"))
        self.repost_group_tab.source_edit.setText(self.cfg.get("REPOST_GROUP_SOURCE"))
        self.repost_group_tab.author_edit.setText(self.cfg.get("REPOST_GROUP_AUTHOR"))
        self.repost_group_tab.target_edit.setText(self.cfg.get("REPOST_GROUP_TARGET"))
        self.cleaner_tab.channel_edit.setText(self.cfg.get("CHANNEL_ID"))
        self.cleaner_tab.keep_list.clear()
        self.cleaner_tab._load_keep_ids()

    # -------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._any_worker_running():
            answer = QMessageBox.question(
                self, self.i18n.tr("app_title"),
                self.i18n.tr("worker_running"))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for tab in self.tool_tabs:
                if tab.worker:
                    tab.worker.request_cancel()
        event.accept()
