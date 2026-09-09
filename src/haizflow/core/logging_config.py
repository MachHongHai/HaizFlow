import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from haizflow.config import LOGS_DIR

_CONFIGURED = False
_QT_HANDLER = None


def configure_app_logging() -> None:
    """Configure bounded production logging and process-wide exception hooks."""
    global _CONFIGURED, _QT_HANDLER
    if _CONFIGURED:
        return

    os.makedirs(LOGS_DIR, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for existing in tuple(root_logger.handlers):
        if isinstance(existing, RotatingFileHandler) and existing.baseFilename == handler.baseFilename:
            existing.close()
            root_logger.removeHandler(existing)
    root_logger.addHandler(handler)

    sys.excepthook = _handle_unhandled_exception
    threading.excepthook = _handle_thread_exception
    sys.unraisablehook = _handle_unraisable_exception

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        levels = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }

        def qt_message_handler(message_type, context, message):
            source = ""
            if context and getattr(context, "file", None):
                source = f" ({context.file}:{getattr(context, 'line', 0)})"
            logging.getLogger("qt").log(levels.get(message_type, logging.INFO), "%s%s", message, source)

        _QT_HANDLER = qt_message_handler
        qInstallMessageHandler(_QT_HANDLER)
    except (ImportError, RuntimeError):
        logging.getLogger(__name__).exception("Could not install the Qt message handler")

    _CONFIGURED = True


def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))


def _handle_thread_exception(args) -> None:
    if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
        return
    logging.critical(
        "Unhandled exception in thread %s",
        getattr(args.thread, "name", "unknown"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _handle_unraisable_exception(args) -> None:
    logging.error(
        "Unraisable exception in %r: %s",
        getattr(args, "object", None),
        getattr(args, "err_msg", None) or "no detail",
        exc_info=(type(args.exc_value), args.exc_value, args.exc_traceback),
    )
