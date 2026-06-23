# stratos/logging_config.py
"""
Structured logging configuration for StratOS.
Uses JSON format for production, human-readable for development.
"""
import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any
from stratos.config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
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
        
        return json.dumps(log_data)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for development."""
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
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
    if settings.environment == "production":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(HumanFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    
    return root_logger


# Create a logger for StratOS
logger = logging.getLogger("stratos")


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(f"stratos.{name}")


# Helper for structured logging with extra fields
def log_with_context(logger: logging.Logger, level: str, message: str, **kwargs):
    """Log a message with additional context fields."""
    extra = {}
    
    # Map common fields
    field_mapping = {
        "run_id": "run_id",
        "competitor": "competitor",
        "agent": "agent",
        "provider": "provider",
    }
    
    for key, value in kwargs.items():
        if key in field_mapping:
            extra[field_mapping[key]] = value
    
    getattr(logger, level)(message, extra=extra if extra else None)


# Auto-setup on import
setup_logging()