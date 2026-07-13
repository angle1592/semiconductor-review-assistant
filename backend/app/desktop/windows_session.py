from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable


class SessionEndHandler:
    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016

    def __init__(self, shutdown: Callable[[], None]):
        self._shutdown = shutdown
        self._requested = False

    def handle(self, message: int, wparam: int) -> int | None:
        if message == self.WM_QUERYENDSESSION:
            self._request_shutdown()
            return 1
        if message == self.WM_ENDSESSION and wparam:
            self._request_shutdown()
            return 0
        return None

    def _request_shutdown(self) -> None:
        if not self._requested:
            self._requested = True
            self._shutdown()


class WindowsSessionMonitor:
    def __init__(self, shutdown: Callable[[], None]):
        self._handler = SessionEndHandler(shutdown)
        self._window: int | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._thread is None:
            return
        self._ready.wait(timeout=2)
        if self._window is not None:
            import win32con
            import win32gui

            win32gui.PostMessage(self._window, win32con.WM_CLOSE, 0, 0)
        self._thread.join(timeout=2)

    def _run(self) -> None:
        import win32api
        import win32con
        import win32gui

        class_name = f"SemiconductorReviewSession_{os.getpid()}_{uuid.uuid4().hex}"

        def window_proc(window, message, wparam, lparam):
            handled = self._handler.handle(message, wparam)
            if handled is not None:
                return handled
            if message == win32con.WM_CLOSE:
                win32gui.DestroyWindow(window)
                return 0
            if message == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(window, message, wparam, lparam)

        window_class = win32gui.WNDCLASS()
        window_class.hInstance = win32api.GetModuleHandle(None)
        window_class.lpszClassName = class_name
        window_class.lpfnWndProc = window_proc
        atom = win32gui.RegisterClass(window_class)
        try:
            self._window = win32gui.CreateWindowEx(
                0,
                atom,
                "SemiconductorReviewSession",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                window_class.hInstance,
                None,
            )
            self._ready.set()
            win32gui.PumpMessages()
        finally:
            self._ready.set()
            self._window = None
            try:
                win32gui.UnregisterClass(class_name, window_class.hInstance)
            except win32gui.error:
                pass
