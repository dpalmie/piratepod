from typing import Any

from piratepod_core.urls import ensure_url_scheme
from pydantic import BaseModel, Field, HttpUrl, field_validator


class GenerateRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1)
    title: str | None = None

    @field_validator("urls", mode="before")
    @classmethod
    def _ensure_scheme(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [ensure_url_scheme(item) for item in v]
        return v


class SourceResponse(BaseModel):
    title: str
    url: str
    markdown: str


class GenerateResponse(BaseModel):
    urls: list[str]
    sources: list[SourceResponse]
    title: str
    script: str
    audio_path: str
    audio_format: str
    feed_url: str
    episode_id: str
    episode_audio_url: str


class IngestResponse(SourceResponse):
    pass


class ScriptgenResponse(BaseModel):
    script: str


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
