"""
Central configuration management for the VVR Scraper using Pydantic Settings.
This provides type validation and fail-fast environment variable loading.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core API Keys ---
    openai_api_key: str | None = Field(None, alias="VVR_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="VVR_BASE_URL")
    elevenlabs_api_key: str | None = Field(None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("ywBZEqUhld86Jeajq94o", alias="VVR_NARRATOR_VOICE_ID")

    # --- Server Settings ---
    web_host: str = Field("127.0.0.1", alias="WEB_HOST")
    web_port: int = Field(8000, alias="WEB_PORT")
    opds_password: str = Field("password", alias="OPDS_PASSWORD")

    # --- Freesound Settings ---
    freesound_client_id: str | None = Field(None, alias="FREESOUND_CLIENT_ID")
    freesound_client_secret: str | None = Field(None, alias="FREESOUND_CLIENT_SECRET")

    # --- Feature Flags ---
    debug: bool = Field(False, alias="VVR_DEBUG")

    @property
    def is_audio_drama_ready(self) -> bool:
        """Check if essential keys for Audio Drama are present."""
        return bool(self.openai_api_key and self.elevenlabs_api_key)

# Global settings instance
settings = Settings()
