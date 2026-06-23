# stratos/retry.py
"""
Retry logic with exponential backoff for external services.
Uses tenacity for robust error handling.
"""
import asyncio
from typing import Type, List, Callable, Any, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
    before_sleep_log,
    after_log,
)
import logging
from stratos.logging_config import get_logger

logger = get_logger("retry")


# Common exception types to retry on
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    ConnectionResetError,
    BrokenPipeError,
    # Add HTTP/network exceptions
)


def is_retryable_error(exception: Exception) -> bool:
    """
    Determine if an exception should trigger a retry.
    
    Returns True for network errors, timeouts, rate limits, etc.
    """
    # Check if it's a known retryable exception type
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True
    
    # Check for specific error messages
    error_msg = str(exception).lower()
    retryable_keywords = [
        "timeout",
        "connection",
        "rate limit",
        "too many requests",
        "429",
        "503",
        "504",
        "network",
        "unreachable",
        "temporary",
        "retry",
    ]
    
    return any(keyword in error_msg for keyword in retryable_keywords)


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    operation_name: str = "operation",
):
    """
    Decorator for retry logic with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        min_wait: Minimum wait time in seconds (base for exponential)
        max_wait: Maximum wait time in seconds
        retry_on_exceptions: List of exception types to retry on
        operation_name: Name of the operation for logging
    
    Usage:
        @with_retry(max_attempts=3, operation_name="scrape")
        async def scrape_url(url):
            ...
    """
    # Determine which exceptions to retry on
    if retry_on_exceptions is None:
        retry_on_exceptions = [Exception]  # Retry on any exception by default
    
    # Build the retry condition
    def should_retry(exception: Exception) -> bool:
        # Check if exception is in the list
        for exc_type in retry_on_exceptions:
            if isinstance(exception, exc_type):
                return True
        # Also check if it's a retryable error
        return is_retryable_error(exception)
    
    def decorator(func):
        # Apply tenacity retry
        retry_decorator = retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
            retry=retry_if_exception(should_retry),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            after=after_log(logger, logging.INFO),
            reraise=True,
        )
        
        # Apply the retry decorator
        wrapped_func = retry_decorator(func)
        
        # Preserve the original function name
        wrapped_func.__name__ = func.__name__
        wrapped_func.__doc__ = func.__doc__
        
        return wrapped_func
    
    return decorator


class AsyncRetryContext:
    """
    Context manager for retrying blocks of code with exponential backoff.
    
    Usage:
        async with AsyncRetryContext(max_attempts=3) as retry:
            async for attempt in retry:
                try:
                    result = await risky_operation()
                    retry.success(result)
                except Exception as e:
                    retry.fail(e)
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 30.0,
        operation_name: str = "operation",
    ):
        self.max_attempts = max_attempts
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.operation_name = operation_name
        self.attempt = 0
        self.result = None
        self.last_error = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def __aiter__(self):
        self.attempt = 0
        return self
    
    async def __anext__(self):
        self.attempt += 1
        
        if self.attempt > self.max_attempts:
            # Out of attempts, raise the last error
            if self.last_error:
                raise self.last_error
            raise RuntimeError(f"{self.operation_name} failed after {self.max_attempts} attempts")
        
        # Calculate wait time (exponential backoff)
        wait_time = min(
            self.min_wait * (2 ** (self.attempt - 1)),
            self.max_wait
        )
        
        if self.attempt > 1:
            logger.warning(
                f"Retry {self.attempt}/{self.max_attempts} for {self.operation_name} "
                f"after {wait_time:.1f}s"
            )
            await asyncio.sleep(wait_time)
        
        return self
    
    def success(self, result):
        """Mark the operation as successful with the given result."""
        self.result = result
        # Signal that we're done by setting attempt beyond max
        self.attempt = self.max_attempts + 1
    
    def fail(self, error: Exception):
        """Mark the operation as failed with the given error."""
        self.last_error = error


# Convenience function for retrying with async context manager
async def retry_async(
    func: Callable,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    *args,
    **kwargs,
) -> Any:
    """
    Retry an async function with exponential backoff.
    
    Usage:
        result = await retry_async(
            scrape_url,
            max_attempts=3,
            url="https://example.com"
        )
    """
    attempt = 0
    last_error = None
    
    while attempt < max_attempts:
        attempt += 1
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            
            if attempt < max_attempts:
                wait_time = min(min_wait * (2 ** (attempt - 1)), max_wait)
                logger.warning(
                    f"Retry {attempt}/{max_attempts} for {func.__name__} "
                    f"after {wait_time:.1f}s: {e}"
                )
                await asyncio.sleep(wait_time)
    
    raise last_error