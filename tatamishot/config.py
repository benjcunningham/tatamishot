from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    plex_url: str = "http://localhost:32400"
    plex_token: str = ""
    output_dir: str = "/output"
    host: str = "0.0.0.0"
    port: int = 8484
    media_dir: str = ""
    media_dir_container: str = "/media"


settings = Settings()
