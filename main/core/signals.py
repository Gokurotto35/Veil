#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signal handlers for graceful shutdown
"""

import os
import signal
import sys

import utils.integration.pengu_loader as pengu_loader
from utils.core.logging import get_logger

from .state import get_app_state

log = get_logger()


def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown"""
    app_state = get_app_state()
    if app_state.shutting_down:
        return  # Prevent multiple shutdown attempts
    app_state.shutting_down = True
    
    print(f"\nReceived signal {signum}, initiating graceful shutdown...")
    try:
        pengu_loader.deactivate_on_exit()
    except Exception:
        log.warning("Failed to deactivate Pengu Loader during shutdown", exc_info=True)
    # Let run_league_unlock() reach its finally block so the thread manager,
    # tray and injection processes are cleaned up as well.  The direct Pengu
    # deactivation above remains a safety net for signals received early in
    # startup, before the main cleanup scope exists.
    raise KeyboardInterrupt


def force_quit_handler():
    """Force quit handler that can be called from anywhere"""
    app_state = get_app_state()
    if app_state.shutting_down:
        return
    app_state.shutting_down = True
    
    print("\nForce quit initiated...")
    try:
        pengu_loader.deactivate_on_exit()
    except Exception:
        log.warning("Failed to deactivate Pengu Loader during shutdown", exc_info=True)
    os._exit(0)


def _start_shutdown_watcher() -> None:
    """Spawn a hidden top-level window that deactivates Pengu on WM_ENDSESSION.

    Windows delivers WM_QUERYENDSESSION / WM_ENDSESSION to every top-level
    window when the session is ending (logoff, restart, shutdown).  This is
    the only reliable way to run cleanup in a tray / GUI application —
    SetConsoleCtrlHandler is not guaranteed to fire.

    The window and its message pump live on a daemon thread so they don't
    block normal shutdown through Python's exit machinery.
    """
    import ctypes
    from ctypes import wintypes
    import threading

    # Private DLL instances: the prototypes below must not leak onto the
    # shared ctypes.windll objects the rest of Veil calls with defaults
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016
    ERROR_CLASS_ALREADY_EXISTS = 1410

    # -- Minimal type scaffolding ------------------------------------------------
    pointer_size = ctypes.sizeof(ctypes.c_void_p)
    LRESULT = (
        getattr(wintypes, "LRESULT", None)
        or (ctypes.c_longlong if pointer_size == 8 else ctypes.c_long)
    )
    WPARAM = getattr(wintypes, "WPARAM", ctypes.c_ulonglong if pointer_size == 8 else ctypes.c_ulong)
    LPARAM = getattr(wintypes, "LPARAM", ctypes.c_longlong if pointer_size == 8 else ctypes.c_long)

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

    HCURSOR = getattr(wintypes, "HCURSOR", wintypes.HANDLE)
    HICON = getattr(wintypes, "HICON", wintypes.HANDLE)
    HBRUSH = getattr(wintypes, "HBRUSH", wintypes.HANDLE)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", HICON),
            ("hCursor", HCURSOR),
            ("hbrBackground", HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", HICON),
        ]

    # Without these the default c_int restype truncates 64-bit handles
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT

    # -- Window procedure --------------------------------------------------------
    @WNDPROC
    def _wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_QUERYENDSESSION:
            return 1  # agree to end the session
        if msg == WM_ENDSESSION:
            if wparam:  # session is actually ending
                app_state = get_app_state()
                if not app_state.shutting_down:
                    app_state.shutting_down = True
                    try:
                        pengu_loader.deactivate_on_exit()
                    except Exception:
                        log.warning("Failed to deactivate Pengu Loader on session end", exc_info=True)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # prevent GC of the callback
    _start_shutdown_watcher._prevent_gc = _wnd_proc  # type: ignore[attr-defined]

    # -- Thread body -------------------------------------------------------------
    def _run() -> None:
        class_name = "VeilShutdownWatcher"
        h_instance = kernel32.GetModuleHandleW(None)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = _wnd_proc
        wc.hInstance = h_instance
        wc.lpszClassName = class_name

        if not user32.RegisterClassExW(ctypes.byref(wc)):
            error = ctypes.get_last_error()
            if error != ERROR_CLASS_ALREADY_EXISTS:
                log.warning(f"Shutdown watcher: RegisterClassExW failed (error {error})")
                return

        # Create a regular (non-message-only) top-level window so it receives
        # broadcast messages like WM_QUERYENDSESSION.  It is never shown.
        hwnd = user32.CreateWindowExW(
            0,             # no extended style
            class_name,
            "Veil Shutdown Watcher",
            0,             # no visible style flags
            0, 0, 0, 0,   # position / size irrelevant
            None,          # no parent → top-level
            None,
            h_instance,
            None,
        )
        if not hwnd:
            log.warning(f"Shutdown watcher: CreateWindowExW failed (error {ctypes.get_last_error()})")
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    t = threading.Thread(target=_run, name="ShutdownWatcher", daemon=True)
    t.start()


def setup_signal_handlers() -> None:
    """Set up signal handlers"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # On Windows, create a hidden top-level window whose sole purpose is to
    # receive WM_QUERYENDSESSION / WM_ENDSESSION when the user logs off or
    # shuts down the PC.  SetConsoleCtrlHandler does NOT reliably fire for
    # tray / GUI applications, but WM_ENDSESSION is always delivered to
    # top-level windows.
    if sys.platform == "win32":
        _start_shutdown_watcher()

