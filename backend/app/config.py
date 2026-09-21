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
    google_client_id: str = ""
    google_allowed_emails: str = "oshaye@gastrobh.com,fabio@practiceops.ai"
    allowed_origins: str = "http://localhost:3000"
    live_actions_enabled: bool = False
    background_refresh_enabled: bool = False
    dashboard_refresh_seconds: int = 300
    dashboard_state_path: str = ""
    phone_enabled: bool = False
    phone_outbound_enabled: bool = False
    phone_trial_proxy_enabled: bool = False
    phone_live_enabled: bool = False
    phone_fast_reads_enabled: bool = False
    phone_dispatch_model: str = "gpt-5.6-luna"
    phone_pin_required: bool = False
    phone_followup_mode: str = "app"
    phone_live_model: str = "gpt-live-1"
    phone_public_url: str = ""
    phone_bridge_token: str = ""
    phone_callers_json: str = "{}"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    openai_api_key: str = ""
    phone_voice: str = "marin"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]

    @property
    def allowed_google_emails(self) -> set[str]:
        return {value.strip().lower() for value in self.google_allowed_emails.split(",") if value.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
