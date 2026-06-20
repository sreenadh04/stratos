from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings(BaseSettings):
    gemini_api_key: str
    groq_api_key: str = ""
    firecrawl_api_key: str
    slack_webhook_url: str
    database_url: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    langchain_api_key: str = ""
    langsmith_api_key: str = ""
    langchain_tracing_v2: str = "false"
    product_context: str = "StratOS is a competitive intelligence tool for founders and product teams."

    @property
    def tracing_enabled(self) -> bool:
        return self.langchain_tracing_v2.lower() == "true" and bool(self.langsmith_api_key)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


@lru_cache()
def get_settings() -> Settings:
    return settings
