"""Logging simples com arquivos rotativos, sem dependências externas."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from ..core.util import app_data_dir

_LOGGER_NAME = "umc"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    try:
        path = os.path.join(app_data_dir(), "logs")
        os.makedirs(path, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            os.path.join(path, "converter.log"), maxBytes=1_000_000, backupCount=3,
            encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        stream.setLevel(logging.WARNING)
        logger.addHandler(stream)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def log_dir() -> str:
    return os.path.join(app_data_dir(), "logs")
