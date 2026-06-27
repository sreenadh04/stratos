# stratos/retry.py
"""
Retry logic with exponential backoff for external services.
Includes circuit breaker pattern and timeout support.
"""
import asyncio
import time
import functools
from typing import Type, List, Callable, Any, Optional, Dict
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
    before_sleep_log,
    after_log,
    RetryError,
)
import logging
from stratos.logging_config import get_logger

logger = get_logger("retry")


# ============================================================
# RETRYABLE EXCEPTIONS
# ============================================================
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    ConnectionResetError,
    BrokenPipeError,
    asyncio.TimeoutError,
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
        "gateway",
        "bad gateway",
    ]
    
    return any(keyword in error_msg for keyword in retryable_keywords)


# ============================================================
# #25: CIRCUIT BREAKER
# ============================================================
class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation (requests pass through)
    - OPEN: Failing (requests are blocked)
    - HALF_OPEN: Testing if service has recovered
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = "CLOSED"
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Usage:
            result = await circuit_breaker.call(risky_function, arg1, arg2)
        """
        async with self._lock:
            # Check if circuit is OPEN
            if self._state == "OPEN":
                # Check if recovery timeout has elapsed
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    logger.info(f"Circuit '{self.name}' moving to HALF_OPEN")
                    self._state = "HALF_OPEN"
                    self._half_open_calls = 0
                else:
                    raise CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN")
            
            # Check if circuit is HALF_OPEN
            if self._state == "HALF_OPEN":
                self._half_open_calls += 1
                if self._half_open_calls > self.half_open_max_calls:
                    raise CircuitBreakerOpenError(f"Circuit '{self.name}' is in HALF_OPEN state")
        
        try:
            result = await func(*args, **kwargs)
            
            # Success - reset circuit
            async with self._lock:
                if self._state == "HALF_OPEN":
                    logger.info(f"Circuit '{self.name}' reset to CLOSED")
                    self._state = "CLOSED"
                    self._failure_count = 0
                    self._half_open_calls = 0
                else:
                    self._failure_count = 0
            
            return result
            
        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                
                if self._failure_count >= self.failure_threshold:
                    logger.warning(f"Circuit '{self.name}' opened after {self._failure_count} failures")
                    self._state = "OPEN"
            
            raise


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is OPEN."""
    pass


# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name)
    return _circuit_breakers[name]


# ============================================================
# RETRY DECORATOR (#2)
# ============================================================
def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    operation_name: str = "operation",
    use_circuit_breaker: bool = False,
    circuit_breaker_name: str = None,
):
    """
    Decorator for retry logic with exponential backoff.
    Optional circuit breaker support.
    
    Usage:
        @with_retry(max_attempts=3, operation_name="scrape")
        async def scrape_url(url):
            ...
    
        @with_retry(use_circuit_breaker=True, circuit_breaker_name="groq")
        async def call_groq(prompt):
            ...
    """
    # Determine which exceptions to retry on
    if retry_on_exceptions is None:
        retry_on_exceptions = [Exception]
    
    # Build the retry condition
    def should_retry(exception: Exception) -> bool:
        # Check if exception is in the list
        for exc_type in retry_on_exceptions:
            if isinstance(exception, exc_type):
                return True
        # Also check if it's a retryable error
        return is_retryable_error(exception)
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Apply circuit breaker if enabled
            if use_circuit_breaker:
                cb_name = circuit_breaker_name or func.__name__
                circuit_breaker = get_circuit_breaker(cb_name)
                try:
                    return await circuit_breaker.call(func, *args, **kwargs)
                except CircuitBreakerOpenError as e:
                    logger.error(f"Circuit breaker blocked call to {func.__name__}: {e}")
                    raise
            
            # Apply tenacity retry
            retry_decorator = retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
                retry=retry_if_exception(should_retry),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )
            
            wrapped_func = retry_decorator(func)
            return await wrapped_func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================
# #22: TIMEOUT SUPPORT
# ============================================================
async def with_timeout(
    func: Callable,
    timeout_seconds: float = 30.0,
    *args,
    **kwargs,
) -> Any:
    """
    Execute a function with a timeout.
    
    Usage:
        result = await with_timeout(scrape_url, 10.0, "https://example.com")
    """
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")


# ============================================================
# RETRY CONTEXT MANAGER
# ============================================================
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
        self.attempt = self.max_attempts + 1
    
    def fail(self, error: Exception):
        """Mark the operation as failed with the given error."""
        self.last_error = error


# ============================================================
# #5: PARTIAL FAILURE RECOVERY
# ============================================================
# stratos/retry.py (updated function)

async def gather_with_partial_recovery(
    tasks: List[Callable],
    continue_on_failure: bool = True,
    max_retries: int = 2,
) -> List[Any]:
    """
    Execute multiple async tasks with partial failure recovery.
    
    Args:
        tasks: List of async functions to execute
        continue_on_failure: If True, continue with remaining tasks on failure
        max_retries: Number of retries per task
    
    Returns:
        List of results (None for failed tasks)
    """
    results = []
    
    for i, task_func in enumerate(tasks):
        for attempt in range(max_retries + 1):
            try:
                # CALL the function to get the coroutine, then await it
                result = await task_func()
                results.append(result)
                break
            except Exception as e:
                if attempt < max_retries and continue_on_failure:
                    wait = min(1.0 * (2 ** attempt), 10.0)
                    logger.warning(
                        f"Task {i+1}/{len(tasks)} failed (attempt {attempt+1}/{max_retries+1}): {e}. "
                        f"Retrying in {wait:.1f}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Task {i+1}/{len(tasks)} failed permanently: {e}")
                    if continue_on_failure:
                        results.append(None)
                    else:
                        raise
                    break
    
    return results


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================
async def retry_async(
    func: Callable,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    timeout: Optional[float] = None,
    *args,
    **kwargs,
) -> Any:
    """
    Retry an async function with exponential backoff.
    Optional timeout support.
    
    Usage:
        result = await retry_async(
            scrape_url,
            max_attempts=3,
            timeout=10.0,
            url="https://example.com"
        )
    """
    # Apply timeout wrapper if specified
    if timeout:
        return await with_timeout(
            _retry_async_impl,
            timeout,
            func,
            max_attempts,
            min_wait,
            max_wait,
            *args,
            **kwargs
        )
    
    return await _retry_async_impl(func, max_attempts, min_wait, max_wait, *args, **kwargs)


async def _retry_async_impl(
    func: Callable,
    max_attempts: int,
    min_wait: float,
    max_wait: float,
    *args,
    **kwargs,
) -> Any:
    """Internal implementation of retry_async."""
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