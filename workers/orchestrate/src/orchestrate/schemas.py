from typing import Any

from pydantic import BaseModel, HttpUrl, field_validator


class GenerateRequest(BaseModel):
    url: HttpUrl
    title: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, v: Any) -> Any:
        if isinstance(v, str) and "://" not in v:
            return f"https://{v}"
        return v


class GenerateResponse(BaseModel):
    url: str
    title: str
    markdown: str
    script: str
    audio_path: str
    audio_format: str
    feed_url: str
    episode_id: str
    episode_audio_url: str


class IngestResponse(BaseModel):
    title: str
    url: str
    markdown: str


class AudioResponse(BaseModel):
    audio_path: str
    audio_format: str


class PodcastResponse(BaseModel):
    id: str
    slug: str
    title: str
    feed_url: str


class EpisodeResponse(BaseModel):
    id: str
    audio_url: str
