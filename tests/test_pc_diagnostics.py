import logging
from pathlib import Path
import sys
import tempfile
import threading
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pc-app"))
from core.runtime_diagnostics import instalar_diagnostico


class DiagnosticsTests(unittest.TestCase):
    def test_exceptions_are_logged_and_hooks_are_restored(self):
        class Owner:
            def report_callback_exception(self, *args): pass
            def after(self, delay, callback): return "heartbeat"
            def after_cancel(self, token): self.cancelled = token
        owner = Owner()
        sys_hook, thread_hook, tk_hook = sys.excepthook, threading.excepthook, owner.report_callback_exception
        previous_level = logging.getLogger("AuditFlow").level
        with tempfile.TemporaryDirectory() as folder:
            close = instalar_diagnostico(owner, folder)
            try:
                owner.report_callback_exception(ValueError, ValueError("fixture error"), None)
            finally:
                close()
            self.assertIn("fixture error", (Path(folder) / "application.log").read_text(encoding="utf-8"))
        self.assertIs(sys.excepthook, sys_hook)
        self.assertIs(threading.excepthook, thread_hook)
        self.assertEqual(owner.report_callback_exception, tk_hook)
        self.assertEqual(owner.cancelled, "heartbeat")
        logging.getLogger("AuditFlow").setLevel(previous_level)
