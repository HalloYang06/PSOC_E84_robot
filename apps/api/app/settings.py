from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DEV_SECRET_KEY = "dev-session-secret-local-only"
DEFAULT_DEV_TOKEN_ENCRYPTION_KEY = "dev-token-key-local-only"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "sqlite:///./ai_collab.db"
    redis_url: str = "redis://localhost:6379/0"

    # Safe-by-default runtime switches. Local/test can opt in explicitly.
    secret_key: str = ""
    token_encryption_key: str = ""
    allow_bootstrap_auth: bool = False
    database_auto_create: bool = False
    database_auto_seed: bool = False
    runner_registration_token: str = ""

    auth_provider: str = "legacy"

    supertokens_connection_uri: str = ""
    supertokens_api_key: str = ""
    supertokens_app_name: str = "AI协作平台"
    supertokens_api_domain: str = "http://127.0.0.1:8000"
    supertokens_website_domain: str = "http://lvh.me:3001"
    supertokens_api_base_path: str = "/api/st-auth"
    supertokens_website_base_path: str = "/auth"
    supertokens_email_verification_mode: str = "REQUIRED"
    cors_allowed_origins: str = ""
    supertokens_cookie_secure: str = ""

    supertokens_smtp_host: str = ""
    supertokens_smtp_port: int = 587
    supertokens_smtp_username: str = ""
    supertokens_smtp_password: str = ""
    supertokens_smtp_from_name: str = "AI协作平台"
    supertokens_smtp_from_email: str = ""
    supertokens_smtp_secure: bool = False

    @property
    def auth_provider_normalized(self) -> str:
        return self.auth_provider.strip().lower()

    @property
    def supertokens_enabled(self) -> bool:
        return self.auth_provider_normalized == "supertokens" and bool(self.supertokens_connection_uri.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        raw = self.cors_allowed_origins.strip()
        if not raw:
            website_domain = self.supertokens_website_domain.strip()
            return [website_domain] if website_domain else []
        origins: list[str] = []
        for item in raw.replace(",", "\n").splitlines():
            candidate = item.strip()
            if candidate and candidate not in origins:
                origins.append(candidate)
        return origins

    @property
    def supertokens_cookie_secure_override(self) -> bool | None:
        raw = self.supertokens_cookie_secure.strip().lower()
        if not raw:
            return None
        return raw in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
