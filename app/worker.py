"""Background worker: runs one async tool on its own asyncio loop in a QThread.

The GUI thread never blocks. Login prompts (SMS code, 2FA password) are
bridged to the GUI via `sig_ask` — the worker thread blocks on a
threading.Event until the dialog answers via `provide_answer()`.
"""
from __future__ import annotations

import asyncio
import threading
import traceback

from PySide6.QtCore import QThread, Signal


class Ctx:
    """Callbacks handed to tool coroutines."""

    def __init__(self, worker: "ToolWorker") -> None:
        self._w = worker

    def log(self, msg: str) -> None:
        self._w.sig_log.emit(str(msg))

    def progress(self, done: int, total: int) -> None:
        # total == 0 -> indeterminate
        self._w.sig_progress.emit(int(done), int(total))

    def cancelled(self) -> bool:
        return self._w.cancel_requested


class ToolWorker(QThread):
    sig_log = Signal(str)
    sig_progress = Signal(int, int)         # done, total (0 = unknown)
    sig_done = Signal(bool, str)            # ok, message
    sig_ask = Signal(str, str)              # kind ('code'|'password'), prompt

    def __init__(self, tool_func, params: dict, conn: dict, parent=None) -> None:
        """conn: {'api_id','api_hash','phone','session'}"""
        super().__init__(parent)
        self.tool_func = tool_func
        self.params = params
        self.conn = conn
        self.cancel_requested = False
        self._answer: str | None = None
        self._evt = threading.Event()

    # ------------------------------------------------- GUI-thread methods
    def request_cancel(self) -> None:
        self.cancel_requested = True
        self._evt.set()  # unblock a pending login prompt, if any

    def provide_answer(self, value: str) -> None:
        self._answer = value
        self._evt.set()

    # ----------------------------------------------- worker-thread methods
    def _ask(self, kind: str, prompt: str) -> str:
        self._evt.clear()
        self._answer = None
        self.sig_ask.emit(kind, prompt)
        self._evt.wait()
        if self.cancel_requested or self._answer is None:
            raise RuntimeError("Login cancelled")
        return self._answer

    def run(self) -> None:  # QThread entry
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._main())
            self.sig_done.emit(not self.cancel_requested, result or "")
        except Exception as exc:  # noqa: BLE001 - surfaced to the GUI log
            self.sig_log.emit(traceback.format_exc())
            self.sig_done.emit(False, str(exc))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    async def _main(self) -> str:
        from telethon import TelegramClient

        ctx = Ctx(self)
        client = TelegramClient(
            self.conn["session"], int(self.conn["api_id"]), self.conn["api_hash"]
        )
        ctx.log("Connecting to Telegram…")
        await client.start(
            phone=lambda: self.conn["phone"],
            code_callback=lambda: self._ask("code", "code"),
            password=lambda: self._ask("password", "password"),
        )
        me = await client.get_me()
        ctx.log(f"Connected as {getattr(me, 'first_name', '')} "
                f"(+{getattr(me, 'phone', '?')}).")
        try:
            return await self.tool_func(client, self.params, ctx)
        finally:
            await client.disconnect()
