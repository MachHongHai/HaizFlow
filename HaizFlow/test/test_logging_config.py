import logging
import sys
import tempfile
import threading
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core import logging_config


class LoggingConfigTest(unittest.TestCase):
    def test_logging_is_bounded_idempotent_and_installs_exception_hooks(self):
        root_logger = logging.getLogger()
        original_handlers = tuple(root_logger.handlers)
        original_level = root_logger.level
        original_excepthook = sys.excepthook
        original_thread_hook = threading.excepthook
        original_unraisable_hook = sys.unraisablehook
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            logging_config, "LOGS_DIR", temp_dir
        ), patch("PySide6.QtCore.qInstallMessageHandler") as qt_handler:
            logging_config._CONFIGURED = False
            try:
                logging_config.configure_app_logging()
                logging_config.configure_app_logging()
                added = [
                    handler
                    for handler in root_logger.handlers
                    if handler not in original_handlers and isinstance(handler, RotatingFileHandler)
                ]
                self.assertEqual(len(added), 1)
                self.assertEqual(added[0].maxBytes, 5 * 1024 * 1024)
                self.assertEqual(added[0].backupCount, 3)
                self.assertIs(sys.excepthook, logging_config._handle_unhandled_exception)
                self.assertIs(threading.excepthook, logging_config._handle_thread_exception)
                self.assertIs(sys.unraisablehook, logging_config._handle_unraisable_exception)
                qt_handler.assert_called_once()
            finally:
                for handler in tuple(root_logger.handlers):
                    if handler not in original_handlers:
                        root_logger.removeHandler(handler)
                        handler.close()
                sys.excepthook = original_excepthook
                threading.excepthook = original_thread_hook
                sys.unraisablehook = original_unraisable_hook
                root_logger.setLevel(original_level)
                logging_config._CONFIGURED = False


if __name__ == "__main__":
    unittest.main()
