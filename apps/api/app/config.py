from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── OpenRouter (multi-key, takes priority when set) ──────
    openrouter_api_keys: str | None = None   # comma-separated OR keys
    openrouter_model: str = "google/gemma-3-27b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Legacy single-key OpenAI-compatible backend ──────────
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    # ── Storage ──────────────────────────────────────────────
    database_url: str = "sqlite:///./veronica.db"
    redis_url: str | None = None
    vector_database_url: str | None = None

    # ── Google OAuth ─────────────────────────────────────────
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/oauth/google/callback"
    frontend_url: str = "http://localhost:3000"

    # ── User identity ─────────────────────────────────────────
    sender_name: str = "Parth Soni"

    # ── App ──────────────────────────────────────────────────
    app_name: str = "VERONICA"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def openrouter_keys_list(self) -> list[str]:
        if not self.openrouter_api_keys:
            return []
        return [k.strip() for k in self.openrouter_api_keys.split(",") if k.strip()]


settings = Settings()
