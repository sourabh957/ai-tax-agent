from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    domain_name: str = Field(default="")

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

    # Auth
    oidc_issuer_url: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: SecretStr = Field(
        default="",
        json_schema_extra={"sensitive": True},
    )
    oidc_audience: str = Field(default="")
    jwt_secret_key: SecretStr = Field(
        default="",
        json_schema_extra={"sensitive": True},
    )

    # Agent limits
    max_agent_iterations: int = Field(default=8)
    max_tool_calls: int = Field(default=10)
    max_llm_calls: int = Field(default=6)

    # Rate limiting
    daily_request_limit: int = Field(default=5)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated string or list")

    @model_validator(mode="after")
    def validate_bedrock(self) -> "Settings":
        if self.llm_provider == "bedrock" and not self.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required when LLM_PROVIDER=bedrock")
        if self.llm_provider == "bedrock" and not self.aws_region:
            raise ValueError("AWS_REGION is required when LLM_PROVIDER=bedrock")
        return self

    @property
    def oidc_client_secret_value(self) -> str:
        return self.oidc_client_secret.get_secret_value()

    @property
    def jwt_secret_key_value(self) -> str:
        return self.jwt_secret_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
