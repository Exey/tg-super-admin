"""TG Admin Tools — entry point.

Responsibilities before anything else imports:
1. Configure logging (console + rotating file in the OS-appropriate location).
2. Create QApplication and show the main window.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

APP_NAME = "TgAdminTools"


def _log_dir() -> Path:
    """OS-appropriate log directory.

    macOS:   ~/Library/Logs/TgAdminTools/
    Windows: %LOCALAPPDATA%/TgAdminTools/logs/
    Linux:   $XDG_STATE_HOME/tgadmintools/ or ~/.local/state/tgadmintools/
    """
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else home) / APP_NAME / "logs"
    xdg = os.environ.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else home / ".local" / "state") / APP_NAME.lower()


def _configure_logging() -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tgadmintools.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:  # avoid duplicates on re-import (pytest-qt etc.)
        return

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file.setFormatter(fmt)
    root.addHandler(file)

    logging.getLogger("telethon").setLevel(logging.WARNING)


def main() -> int:
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info(
        "%s starting (platform=%s, python=%s)",
        APP_NAME, sys.platform, sys.version.split()[0],
    )

    # Import Qt lazily so logging is live if the import itself blows up.
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("TG Admin Tools")
    app.setOrganizationName(APP_NAME)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
