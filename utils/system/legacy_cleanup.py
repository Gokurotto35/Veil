#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remove what Rose, the app Veil was forked from, left on this machine

Veil replaces Rose in place (same installer AppId) but keeps nothing of it:
Rose's League hook, its auto-start task, the ROSE-* plugins and its
%LOCALAPPDATA%\\Rose folder would otherwise stay, and League would load
Rose's plugins next to Veil's. This is the only module allowed to name Rose.

Each step is a no-op once there is nothing left, so it runs on every start.
%LOCALAPPDATA%\\Veil is never touched: another app, VoidVeil, keeps its data
there.
"""

import ctypes
import re
import shutil
import subprocess
import sys
from pathlib import Path

from utils.core.logging import get_logger
from utils.core.paths import get_user_data_dir
from utils.integration import pengu_loader

log = get_logger()

ROSE_MUTEX = r"Local\RoseSingleInstance"
ROSE_TASK = "Rose"
ROSE_FOLDER = "Rose"
ROSE_PLUGIN_PREFIX = "ROSE-"
_SYNCHRONIZE = 0x00100000
_CREATE_NO_WINDOW = 0x08000000


def _rose_is_running() -> bool:
    """Rose holds its single-instance mutex while it runs."""
    if sys.platform != "win32":
        return False
    handle = ctypes.windll.kernel32.OpenMutexW(_SYNCHRONIZE, False, ROSE_MUTEX)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _rose_dir() -> Path:
    """%LOCALAPPDATA%\\Rose of the user Veil runs for, next to Veil's own folder."""
    return get_user_data_dir().parent / ROSE_FOLDER


def _is_rose_dir(path: Path) -> bool:
    """A folder Rose left: "Rose" is a generic name another app may use too."""
    if not path.is_dir():
        return False
    logs = path / "logs"
    return ((path / "Pengu Loader").is_dir() or (path / "config.ini").is_file()
            or (logs.is_dir() and any(logs.glob("rose_*.log*")))
            or (logs.is_dir() and any(logs.glob("log_updater_*.log"))))


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True,
                          creationflags=_CREATE_NO_WINDOW, check=False)


def _delete_task() -> bool:
    """Delete the auto-start task Rose made: one named Rose that runs Rose.exe
    (or Veil.exe, which an earlier Veil installer pointed it at)."""
    query = _schtasks("/Query", "/TN", ROSE_TASK, "/XML")
    if query.returncode != 0 or not re.search(r"(?i)\\(rose|veil)\.exe", query.stdout or ""):
        return False
    return _schtasks("/Delete", "/TN", ROSE_TASK, "/F").returncode == 0


def _delete_tree(path: Path) -> bool:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        # League keeps Rose's core.dll loaded until it closes: next start
        log.warning("[Cleanup] Could not remove %s yet, will retry on the next start: %s", path, exc)
        return False
    return True


def remove_legacy_leftovers() -> list[str]:
    """Remove Rose's hook, task, plugins and folder; returns what was removed. Never raises."""
    removed: list[str] = []
    try:
        if _rose_is_running():
            log.info("[Cleanup] Rose is running: its leftovers stay until it exits")
            return removed

        rose_dir = _rose_dir()
        if pengu_loader.remove_hook_into(rose_dir):
            removed.append(f"League hook into {rose_dir}")
        if _delete_task():
            removed.append(f"scheduled task {ROSE_TASK}")

        bundled = pengu_loader._get_bundled_pengu_dir()
        plugins = bundled / "plugins" if bundled else None
        if plugins and plugins.is_dir():
            for plugin in plugins.iterdir():
                if plugin.is_dir() and plugin.name.startswith(ROSE_PLUGIN_PREFIX) and _delete_tree(plugin):
                    removed.append(f"plugin {plugin}")

        if _is_rose_dir(rose_dir) and _delete_tree(rose_dir):
            removed.append(f"folder {rose_dir}")
    except Exception:
        log.exception("[Cleanup] Removing Rose's leftovers failed")

    for entry in removed:
        log.info("[Cleanup] Removed %s", entry)
    return removed
