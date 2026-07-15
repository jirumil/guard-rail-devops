"""
Shared logging setup — stdout only, no file handlers, ever.

Azure Container Apps (and Docker generally) captures whatever a container
writes to stdout/stderr and ships it to Log Analytics automatically. That
means the correct production logging strategy is "print structured lines
to stdout" — not writing to a log file inside the container, which would
need its own volume, rotation policy, and cleanup story for zero benefit
(the platform already collects stdout for you).

configure_logging() is idempotent: calling it twice for the same service
name is a safe no-op rather than a duplicate-handler bug. This matters
specifically because pytest imports app.py / worker.py once per test
session, and gunicorn's multi-worker model can import the module more
than once per process — neither should ever produce doubled-up log lines.
"""

import logging
import sys

_configured_loggers = set()


def configure_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(service_name)

    if service_name in _configured_loggers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt=(
            '{"timestamp":"%(asctime)s","service":"%(name)s",'
            '"level":"%(levelname)s","message":"%(message)s"}'
        ),
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = (
        False  # don't also hand lines to the root logger — avoids duplicate output
    )

    _configured_loggers.add(service_name)
    return logger
