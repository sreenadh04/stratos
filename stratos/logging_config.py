# stratos/logging_config.py
"""
Structured logging configuration for StratOS.
Uses JSON format for production, human-readable for development.
Supports run_id correlation and audit logging.
"""
import logging
import sys
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from stratos.config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, "run_id"):
            log_data["run_id"] = record.run_id
        if hasattr(record, "competitor"):
            log_data["competitor"] = record.competitor
        if hasattr(record, "agent"):
            log_data["agent"] = record.agent
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        return json.dumps(log_data)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for development."""
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        name = record.name
        message = record.getMessage()
        
        # Add run_id if present
        run_id = getattr(record, "run_id", "")
        if run_id:
            return f"[{timestamp}] {level:8} [{name}] [run:{run_id[:8]}] {message}"
        
        return f"[{timestamp}] {level:8} [{name}] {message}"


def setup_logging():
    """Configure logging with appropriate formatters."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Use JSON formatter for production, human-readable for dev
    if settings.is_production:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(HumanFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return root_logger


# ============================================================
# #26: LOGGER WITH RUN ID SUPPORT
# ============================================================
class RunContextLogger:
    """
    Logger wrapper that automatically adds run_id to all log messages.
    
    Usage:
        logger = get_logger("scout")
        run_logger = logger.with_run_id(run_id)
        run_logger.info("Scout started")
    """
    
    def __init__(self, logger: logging.Logger, run_id: Optional[str] = None):
        self.logger = logger
        self.run_id = run_id
    
    def _log(self, level: str, message: str, **kwargs):
        extra = kwargs.get("extra", {})
        if self.run_id:
            extra["run_id"] = self.run_id
        kwargs["extra"] = extra
        getattr(self.logger, level)(message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log("debug", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log("info", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log("warning", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log("error", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log("critical", message, **kwargs)


# ============================================================
# #36: AUDIT LOGGER
# ============================================================
class AuditLogger:
    """
    Audit logger for tracking user actions.
    Writes to a separate audit log file or database.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("stratos.audit")
        self.logger.setLevel(logging.INFO)
        
        # Add a separate handler for audit logs
        if not any(isinstance(h, AuditHandler) for h in self.logger.handlers):
            handler = AuditHandler()
            handler.setFormatter(JSONFormatter())
            self.logger.addHandler(handler)
    
    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log an audit event."""
        extra = {
            "user_id": user_id,
            "action": action,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "details": details,
            "success": success,
            "error_message": error_message,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }
        self.logger.info(f"Audit: {action}", extra=extra)


class AuditHandler(logging.Handler):
    """Custom handler for audit logs."""
    
    def emit(self, record: logging.LogRecord):
        # This will be written to the audit log file or database
        # For now, just print to stdout with a special prefix
        print(f"[AUDIT] {record.getMessage()}")


# ============================================================
# MAIN LOGGER CREATION
# ============================================================
def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(f"stratos.{name}")


def get_run_logger(name: str, run_id: str) -> RunContextLogger:
    """Get a logger with run_id automatically added."""
    logger = get_logger(name)
    return RunContextLogger(logger, run_id)


# ============================================================
# AUTO-SETUP ON IMPORT
# ============================================================
setup_logging()

# Global audit logger instance
audit_logger = AuditLogger()


# ============================================================
# HELPER: LOG CONFIGURATION
# ============================================================
def log_config() -> None:
    """Log current configuration (for debugging)."""
    from stratos.config import settings
    logger = get_logger("config")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Tracing Enabled: {settings.tracing_enabled}")
    logger.info(f"Dynamic Context Enabled: {settings.dynamic_context_enabled}")