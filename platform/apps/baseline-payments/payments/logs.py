"""Application logging. NPI fields are masked before anything is written."""

import logging

from . import npi

LOGGER_NAME = "payments"


class AppLog:
    def __init__(self, name: str = LOGGER_NAME) -> None:
        self._logger = logging.getLogger(name)

    def info(self, message: str, **fields: object) -> None:
        self._emit(logging.INFO, message, fields)

    def warning(self, message: str, **fields: object) -> None:
        self._emit(logging.WARNING, message, fields)

    def error(self, message: str, **fields: object) -> None:
        self._emit(logging.ERROR, message, fields)

    def _emit(self, level: int, message: str, fields: dict) -> None:
        self._logger.log(level, format_entry(message, mask_fields(fields)))


def mask_fields(fields: dict) -> dict:
    return {key: _masked(key, value) for key, value in fields.items()}


def _masked(key: str, value: object) -> object:
    if not npi.is_npi(key):
        return value
    if value is None:
        return ""
    return npi.mask(key, str(value))


def format_entry(message: str, fields: dict) -> str:
    parts = [message]
    for key in sorted(fields):
        parts.append(f"{key}={fields[key]}")
    return " ".join(parts)


class MemorySink(logging.Handler):
    """Keeps formatted log lines in memory, for local runs and inspection."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []
        self._logger: logging.Logger | None = None
        self._previous_level = logging.NOTSET

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))

    def attach(self, name: str | None = None) -> "MemorySink":
        """Listen on the named logger (the root logger by default) at DEBUG level."""
        self._logger = logging.getLogger(name)
        self._previous_level = self._logger.level
        self._logger.addHandler(self)
        self._logger.setLevel(logging.DEBUG)
        return self

    def detach(self) -> None:
        if self._logger is None:
            return
        self._logger.removeHandler(self)
        self._logger.setLevel(self._previous_level)
        self._logger = None

    def text(self) -> str:
        return "\n".join(self.lines)
