from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database
    database_url: str = Field(default="")

    # Qdrant
    qdrant_url: str = Field(default="")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="")

    # AWS
    aws_region: str = Field(default="")

    # S3
    s3_bucket_name: str = Field(default="")

    # LLM
    llm_provider: Literal["bedrock", "openai", "local"] | None = None
    bedrock_model_id: str = Field(default="")
    llm_api_key: str = Field(default="")

    # Agent limits
    max_agent_iterations: int = Field(default=8)
    max_tool_calls: int = Field(default=10)
    max_llm_calls: int = Field(default=6)

    # Rate limiting
    daily_request_limit: int = Field(default=5)

    @model_validator(mode="after")
    def validate_bedrock(self) -> "Settings":
        if self.llm_provider == "bedrock" and not self.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required when LLM_PROVIDER=bedrock")
        if self.llm_provider == "bedrock" and not self.aws_region:
            raise ValueError("AWS_REGION is required when LLM_PROVIDER=bedrock")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
