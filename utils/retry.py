"""
utils/retry.py
Retry decorator with exponential backoff for API calls.
"""

import time
import functools
from typing import Callable, Type, Tuple

from utils.logger import get_logger

logger = get_logger("retry")


def retry(
    max_attempts: int = 3,
    delay: float = 5.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator: retry a function on failure with exponential backoff.

    Args:
        max_attempts: Total number of tries
        delay: Initial wait between retries (seconds)
        backoff: Multiplier applied to delay each retry
        exceptions: Exception types to catch and retry on
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wait = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        logger.error(
                            f"[{func.__name__}] Failed after {max_attempts} attempts. "
                            f"Last error: {exc}"
                        )
                        raise
                    logger.warning(
                        f"[{func.__name__}] Attempt {attempt}/{max_attempts} failed: {exc}. "
                        f"Retrying in {wait:.1f}s…"
                    )
                    time.sleep(wait)
                    wait *= backoff
        return wrapper
    return decorator
