from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded only from the process environment."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_env: str = "development"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    media_root: Path = Path("/media")
    upload_root: Path = Path("/uploads")
    max_upload_bytes: int = Field(default=21_474_836_480, gt=0)
    upload_hook_secret: str = Field(min_length=32)
    worker_queue: str = "gm-media:jobs"
    worker_heartbeat_key: str = "gm-media:worker:heartbeat"
    worker_heartbeat_ttl_seconds: int = Field(default=45, ge=15, le=300)
    ingest_lease_seconds: int = Field(default=600, ge=60, le=7200)
    media_min_free_bytes: int = Field(default=53_687_091_200, ge=1_073_741_824)
    media_min_free_percent: float = Field(default=15.0, ge=5.0, le=50.0)
    transcription_model_path: Path = Path("/models/faster-whisper-small")
    transcription_device: str = "auto"
    analysis_command_timeout_seconds: int = Field(default=7200, ge=60, le=21_600)
    chatgpt_credential_path: Path = Path("/auth/chatgpt.json")
    chatgpt_model: str = "gpt-6.1-sol"
    ai_gateway_fallback_enabled: bool = False
    ai_gateway_api_key: str = ""
    ai_gateway_model: str = "openai/gpt-6.1-sol"
    editor_request_timeout_seconds: int = Field(default=600, ge=30, le=1800)
    editor_max_context_characters: int = Field(default=120_000, ge=10_000, le=500_000)
    editor_model_refresh_seconds: int = Field(default=21_600, ge=300, le=86_400)
    edit_lease_seconds: int = Field(default=900, ge=60, le=7200)
    visual_encoder_url: str = "http://visual-indexer:8010"
    visual_encoder_timeout_seconds: int = Field(default=120, ge=10, le=600)
    visual_model_path: Path = Path("/models/clip-vit-base-patch32")
    appliance_status_path: Path = Path("/host-status/appliance-health.json")
    tailscale_owner_login: str = ""
    access_internal_secret: str = Field(default="development-access-secret-change-me", min_length=16)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
