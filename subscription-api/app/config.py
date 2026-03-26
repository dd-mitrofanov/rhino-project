from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    INTERNAL_API_URL: str
    INTERNAL_API_TOKEN: str


settings = Settings()  # type: ignore[call-arg]
