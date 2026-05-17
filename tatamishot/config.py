from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    plex_url: str = "http://localhost:32400"
    plex_token: str = ""
    output_dir: str = "/output"
    host: str = "0.0.0.0"
    port: int = 8484
    media_dir_host: str = ""
    media_dir_container: str = "/media"

    class Config:
        env_file = ".env"


settings = Settings()
