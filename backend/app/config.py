from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/ai_chat_room.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    jimo_base_url: str = "https://jimoai-bot-api.xiaohuodui.cn"
    jimo_authorization: str = ""
    jimo_auth_scheme: str = "bearer"
    jimo_chat_endpoint: str = "/v1/chat/completions"
    jimo_timeout_seconds: float = 240.0
    jimo_connect_timeout_seconds: float = 15.0
    jimo_idle_timeout_seconds: float = 45.0
    jimo_streaming: bool = True
    jimo_model_deepseekv4lash: str = ""
    jimo_model_deepseekv4flash: str = ""
    jimo_model_qwen36flash: str = ""
    jimo_model_glm53flash: str = ""
    # Share URLs are optional per-agent overrides. They are kept in the
    # backend environment because share IDs and Authorization values are
    # credentials, not frontend configuration.
    jimo_share_url_deepseekv4lash: str = ""
    jimo_share_url_deepseekv4flash: str = ""
    jimo_share_url_qwen36flash: str = ""
    jimo_share_url_glm53flash: str = ""

    context_message_limit: int = Field(default=20, ge=1, le=200)
    context_character_budget: int = Field(default=24000, ge=1000)
    free_max_messages: int = Field(default=8, ge=1, le=1000)
    free_max_consecutive_messages: int = Field(default=2, ge=1, le=20)
    free_error_threshold: int = Field(default=3, ge=1, le=20)
    ws_ring_buffer_size: int = Field(default=1000, ge=50, le=10000)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_path(self) -> Path | None:
        if not self.database_url.startswith("sqlite"):
            return None
        path = self.database_url.rsplit("/", 1)[-1]
        if path == ":memory:":
            return None
        result = Path(path)
        result.parent.mkdir(parents=True, exist_ok=True)
        return result

    def model_id_for_handle(self, handle: str) -> str:
        mapping = {
            "deepseekv4lash": self.jimo_model_deepseekv4lash or self.jimo_model_deepseekv4flash,
            "deepseekv4flash": self.jimo_model_deepseekv4flash or self.jimo_model_deepseekv4lash,
            "qwen36flash": self.jimo_model_qwen36flash,
            "glm53flash": self.jimo_model_glm53flash,
        }
        return mapping.get(handle, "")

    def share_url_for_handle(self, handle: str) -> str:
        mapping = {
            "deepseekv4lash": self.jimo_share_url_deepseekv4lash or self.jimo_share_url_deepseekv4flash,
            "deepseekv4flash": self.jimo_share_url_deepseekv4flash or self.jimo_share_url_deepseekv4lash,
            "qwen36flash": self.jimo_share_url_qwen36flash,
            "glm53flash": self.jimo_share_url_glm53flash,
        }
        return mapping.get(handle, "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
