from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://champ:champ@db:5432/champ"
    partners_token: str = ""
    partners_id: int = 815138
    partners_base_url: str = "https://pocketpartners.com"
    admin_token: str = "change-me-long-random"
    tg_bot_token: str = ""
    tg_chat_id: str = ""
    site_public_url: str = "http://localhost:3000"
    log_level: str = "INFO"


settings = Settings()
