"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Fireworks ---
    fireworks_api_key: str = ""
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"

    # Model routing. Each agent role maps to a Fireworks model id.
    # gpt-oss-120b honours `reasoning_effort` so it returns clean JSON fast -
    # ideal for the text agents. Kimi K2.6 is the multimodal model (vision) and
    # always reasons heavily, so it's reserved for image diagnosis with a large
    # token budget. DeepSeek V4 Pro (1M ctx) is kept available as a heavy option.
    model_planner: str = "accounts/fireworks/models/gpt-oss-120b"
    model_agent: str = "accounts/fireworks/models/gpt-oss-120b"
    model_vision: str = "accounts/fireworks/models/kimi-k2p6"
    model_fast: str = "accounts/fireworks/models/gpt-oss-120b"
    model_heavy: str = "accounts/fireworks/models/deepseek-v4-pro"
    model_image: str = "accounts/fireworks/models/flux-1-schnell-fp8"
    # Embeddings power the pgvector long-term memory (semantic recall of past
    # consults/diagnoses). Keep `embed_dim` in sync with the model's output size.
    model_embed: str = "nomic-ai/nomic-embed-text-v1.5"
    embed_dim: int = 768

    # --- External data (no synthetic fallbacks) ---
    openweather_api_key: str = ""
    # Defaults to data.gov.in's publicly documented sample key (shared, rate-limited)
    # so market data works without registration; override in .env with your own.
    data_gov_api_key: str = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
    agmarknet_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"

    # --- Twilio (WhatsApp/SMS alerts + inbound Q&A) ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    # WhatsApp sender, e.g. "whatsapp:+14155238886" (Twilio sandbox)
    twilio_whatsapp_from: str = ""

    # --- Autonomous monitoring ---
    monitor_enabled: bool = True
    monitor_interval_hours: float = 24.0
    monitor_start_delay_seconds: float = 30.0

    # Dashboard result (incl. the LLM risk agent) is cached per farm for this long
    # so repeated page loads don't re-spend AI credits. Invalidated on monitor runs
    # and diagnoses; bypass with GET /dashboard?refresh=1.
    dashboard_cache_ttl_minutes: float = 30.0

    # --- Auth (Clerk) ---
    # Issuer like https://your-app.clerk.accounts.dev (dev) or your prod domain.
    clerk_issuer: str = ""
    clerk_secret_key: str = ""  # reserved for Clerk backend API calls if needed

    # --- Database (Render PostgreSQL) ---
    # Render injects DATABASE_URL as postgresql://...; async_database_url adapts it
    # for asyncpg. db_path is retained only for the one-off SQLite import script.
    database_url: str = ""
    db_path: str = "data/krishimitra.db"

    # --- App ---
    app_name: str = "KrishiMitra AI"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL rewritten for the asyncpg driver.

        Accepts the postgres://` / `postgresql://` form Render (and most hosts)
        provide and swaps in the asyncpg driver. Any `sslmode` query param is
        dropped because asyncpg rejects it there - SSL is negotiated automatically
        for managed Postgres, or configured via the engine's connect_args.
        """
        url = self.database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. Point it at your Render Postgres instance."
            )
        parts = urlsplit(url)
        scheme = parts.scheme
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+asyncpg"
        query = "&".join(
            kv for kv in parts.query.split("&") if kv and not kv.startswith("sslmode=")
        )
        return urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
