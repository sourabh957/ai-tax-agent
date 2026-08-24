import logging
import sys
from functools import lru_cache


def configure_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


@lru_cache(maxsize=1)
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
