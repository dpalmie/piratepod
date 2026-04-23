import logging
import os
import sys

import structlog


def configure_logging() -> None:
    """Configure structlog. Pretty in dev (TTY), JSON in prod.

    Env vars:
        LOG_LEVEL   default INFO
        LOG_FORMAT  'json' | 'console' | 'auto' (default auto: console if tty else json)
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("LOG_FORMAT", "auto").lower()

    if fmt == "auto":
        fmt = "console" if sys.stderr.isatty() else "json"

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if fmt == "console"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)
