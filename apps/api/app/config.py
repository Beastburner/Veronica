from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Groq (primary LLM, fast cloud inference) ─────────────
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # ── Ollama (offline fallback) ─────────────────────────────
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"

    # ── Storage ──────────────────────────────────────────────
    database_url: str = "sqlite:///./veronica.db"
    redis_url: str | None = None
    vector_database_url: str | None = None

    # ── Google OAuth ─────────────────────────────────────────
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/oauth/google/callback"
    frontend_url: str = "http://localhost:3000"

    # ── Spotify ──────────────────────────────────────────────
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8000/oauth/spotify/callback"

    # ── Notion ───────────────────────────────────────────────
    notion_api_key: str | None = None

    # ── WhatsApp ─────────────────────────────────────────────
    whatsapp_service_url: str = "http://localhost:3001"

    # ── GitHub ───────────────────────────────────────────────
    github_username: str = "beastburner"
    github_default_repo: str = "Veronica"
    github_token: str | None = None

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


settings = Settings()
