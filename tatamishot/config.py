from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    plex_url: str = "http://localhost:32400"
    output_dir: str = "/output"
    media_dir_host: str = ""
    media_dir: str = "/media"


settings = Settings()
