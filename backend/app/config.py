from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    orgo_api_key: str = ""
    orgo_computer_id: str = "87381d65-cb68-4307-833c-ea9770d07fd1"
    composio_consumer_api_key: str = ""
    composio_personal_gmail_account: str = ""
    composio_personal_calendar_account: str = ""
    dashboard_timezone: str = "America/Los_Angeles"
    dashboard_access_token: str = ""
    allowed_origins: str = "http://localhost:3000"
    live_actions_enabled: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
