# stratos/config.py
"""
Configuration management for StratOS.
Supports both environment variables and dynamic database-based configuration.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from dotenv import load_dotenv
from typing import Optional
import os

load_dotenv(override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ===== API Keys =====
    gemini_api_key: str
    groq_api_key: str = ""
    firecrawl_api_key: str
    slack_webhook_url: str
    
    # ===== Database =====
    database_url: str
    
    # ===== Vector Database =====
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    
    # ===== Observability =====
    langchain_api_key: str = ""
    langsmith_api_key: str = ""
    langchain_tracing_v2: str = "false"
    
    # ===== Product Context =====
    # Static product context (fallback if DB context is not available)
    product_context: str = "StratOS is a competitive intelligence tool for founders and product teams."
    
    # ===== LLM Configuration =====
    llm_provider: str = "groq"  # "groq" or "gemini"
    
    # ===== Scheduler =====
    scheduler_enabled: bool = True
    scheduler_interval_days: int = 7
    scheduler_hour: int = 9
    scheduler_minute: int = 0
    scheduler_run_on_startup: bool = True
    
    # ===== Environment =====
    environment: str = "development"  # "development" or "production"
    
    # ===== API Security =====
    api_key: str = ""
    rate_limit_per_minute: int = 30
    
    # ===== Dynamic Context (Database) =====
    # Enable/disable dynamic product context from database
    dynamic_context_enabled: bool = False
    
    # ===== Feature Flags =====
    enable_circuit_breakers: bool = True
    enable_retry: bool = True
    enable_cost_tracking: bool = False
    
    # ===== Performance =====
    run_timeout_seconds: int = 300  # 5 minutes
    max_concurrent_runs: int = 5
    
    # ===== Monitoring =====
    alerting_enabled: bool = False
    alert_webhook_url: str = ""
    
    # ===== Retention =====
    data_retention_days: int = 180  # 6 months

    @property
    def tracing_enabled(self) -> bool:
        """Check if LangSmith tracing is enabled."""
        return self.langchain_tracing_v2.lower() == "true" and bool(self.langsmith_api_key)
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# ===== Global Settings Instance =====
settings = Settings()


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return settings


# ===== Environment Variable Helper =====
def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Safely get environment variable."""
    return os.getenv(key, default)


# ===== Config Validation =====
def validate_config() -> list[str]:
    """
    Validate configuration and return list of issues.
    Used during startup to catch configuration errors.
    """
    issues = []
    
    # Check required API keys
    if not settings.gemini_api_key:
        issues.append("GEMINI_API_KEY is not set")
    
    if not settings.firecrawl_api_key:
        issues.append("FIRECRAWL_API_KEY is not set")
    
    if not settings.slack_webhook_url:
        issues.append("SLACK_WEBHOOK_URL is not set")
    
    if not settings.database_url:
        issues.append("DATABASE_URL is not set")
    
    # Check LLM provider
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        issues.append("GROQ_API_KEY is not set but llm_provider is 'groq'")
    
    # Check API key in production
    if settings.is_production and not settings.api_key:
        issues.append("API_KEY is not set in production environment")
    
    return issues


# ===== Print Configuration (for debugging) =====
def print_config() -> None:
    """Print current configuration (hides sensitive values)."""
    print("\n" + "=" * 60)
    print("  STRATOS CONFIGURATION")
    print("=" * 60)
    print(f"  Environment: {settings.environment}")
    print(f"  LLM Provider: {settings.llm_provider}")
    print(f"  Scheduler: {'Enabled' if settings.scheduler_enabled else 'Disabled'}")
    print(f"  Tracing: {'Enabled' if settings.tracing_enabled else 'Disabled'}")
    print(f"  Dynamic Context: {'Enabled' if settings.dynamic_context_enabled else 'Disabled'}")
    print(f"  Circuit Breakers: {'Enabled' if settings.enable_circuit_breakers else 'Disabled'}")
    print(f"  Data Retention: {settings.data_retention_days} days")
    print(f"  Run Timeout: {settings.run_timeout_seconds} seconds")
    print(f"  Max Concurrent Runs: {settings.max_concurrent_runs}")
    print("=" * 60)


# Auto-validate on import
if __name__ != "__main__":
    issues = validate_config()
    if issues:
        print("\n⚠️ Configuration Issues Found:")
        for issue in issues:
            print(f"  - {issue}")
        print("")