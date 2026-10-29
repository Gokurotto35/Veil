import ctypes
import subprocess
import sys
import time
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from main.core import signals
from main.core.state import get_app_state

WM_ENDSESSION = 0x0016


def _find_watcher_window(timeout=2.0):
    user32 = ctypes.WinDLL('user32')
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = user32.FindWindowW('VeilShutdownWatcher', None)
        if hwnd:
            return hwnd
        time.sleep(0.02)
    return None


@unittest.skipUnless(sys.platform == 'win32', 'the watcher is a Win32 window')
class ShutdownWatcherTests(unittest.TestCase):
    """GetModuleHandleW was called without a restype, so the 64-bit module
    handle was truncated to 32 bits before reaching RegisterClassExW"""

    def setUp(self):
        self.app_state = get_app_state()
        self.was_shutting_down = self.app_state.shutting_down
        self.app_state.shutting_down = False

    def tearDown(self):
        self.app_state.shutting_down = self.was_shutting_down

    def test_session_end_deactivates_pengu(self):
        signals._start_shutdown_watcher()
        hwnd = _find_watcher_window()
        self.assertTrue(hwnd, 'the watcher window was never created')

        user32 = ctypes.WinDLL('user32')
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        with patch.object(signals.pengu_loader, 'deactivate_on_exit') as deactivate:
            user32.SendMessageW(hwnd, WM_ENDSESSION, 1, 0)

        deactivate.assert_called_once_with()
        self.assertTrue(self.app_state.shutting_down)

    def test_registering_the_window_does_not_fault(self):
        # Windows swallows the access violation inside RegisterClassExW, so
        # the watcher kept working; faulthandler still sees the fault
        script = (
            'import faulthandler, sys; faulthandler.enable()\n'
            'from main.core import signals\n'
            'from main.tests.test_shutdown_watcher import _find_watcher_window\n'
            'sys.exit(0 if _find_watcher_window() else 3)\n'
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotIn('access violation', result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
