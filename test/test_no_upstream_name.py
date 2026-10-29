"""Nothing in the repository may name Rose, the project Veil was forked from.

The legacy cleanup is the only exception: it has to name what it deletes.
"""

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORD = re.compile(r"[A-Za-z0-9_]+")
REAL_WORDS = {"proses", "prosesnya",  # Indonesian locale text
              "microsecond", "microseconds", "inmicroseconds"}  # CEF headers
ALLOWED = {"utils/system/legacy_cleanup.py", "test/test_legacy_cleanup.py", "test/test_no_upstream_name.py"}
ISS = "installer.iss"
ISS_SECTION = ("BEGIN legacy cleanup", "END legacy cleanup")  # in a ; or { } comment


def names_rose(text: str) -> list[str]:
    """Every identifier in text that contains "rose", except REAL_WORDS."""
    return [w for w in WORD.findall(text) if "rose" in w.lower() and w.lower() not in REAL_WORDS]


def tracked_files() -> list[str]:
    output = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [name for name in output.decode("utf-8").split("\0") if name]


def hits_in(name: str) -> list[str]:
    data = (ROOT / name).read_bytes()
    if b"\0" in data:
        return []
    hits = []
    in_section = False
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        if name == ISS and ISS_SECTION[0] in line:
            in_section = True
        if not in_section:
            hits += [f"{name}:{number}: {word}" for word in names_rose(line)]
        if name == ISS and ISS_SECTION[1] in line:
            in_section = False
    return hits


class PatternTests(unittest.TestCase):
    def test_pattern(self):
        for hit in ("ROSE-UI", "window.__roseBridge", "window.RoseI18n", "ROSEJadeLog", "rose_pid",
                    "Rose", "rose-party-relay", "rosedev", "RoseDevSingleInstance"):
            self.assertTrue(names_rose(hit), hit)
        for miss in ("proses", "prosesnya", "microseconds", "InMicroseconds", "Veil"):
            self.assertFalse(names_rose(miss), miss)


class NoRoseTests(unittest.TestCase):
    def test_core_dll_has_no_rose(self):
        core = ROOT / "build" / "pengu-loader" / "core.dll"
        if not core.is_file():
            self.skipTest("core.dll not built")
        data = core.read_bytes()
        self.assertIsNone(re.search(rb"(?i)rose", data))
        self.assertIsNone(re.search(rb"(?i)r\x00o\x00s\x00e\x00", data))

    def test_no_tracked_file_names_rose(self):
        hits = []
        for name in tracked_files():
            if name in ALLOWED or not (ROOT / name).is_file():
                continue
            hits += [f"{name}: path {word}" for word in names_rose(name)]
            hits += hits_in(name)
        self.assertEqual(hits, [], f"{len(hits)} Rose names:\n" + "\n".join(hits[:200]))


if __name__ == "__main__":
    unittest.main()
