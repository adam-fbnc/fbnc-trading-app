from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    schwab_app_key: str
    schwab_app_secret: str
    schwab_callback_url: str = "https://127.0.0.1"

    database_url: str

    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""


settings = Settings()
