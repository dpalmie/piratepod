from typing import Any, Literal

from piratepod_core.urls import ensure_url_scheme
from pydantic import BaseModel, Field, HttpUrl, field_validator

JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobStage = Literal["queued", "ingest", "script", "audio", "publish", "done"]


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
    description: str = ""
    author: str = ""
    cover_url: str = ""
    language: str = "en"
    feed_url: str
    created_at: str = ""


class EpisodeResponse(BaseModel):
    id: str
    podcast_id: str = ""
    title: str = ""
    description: str = ""
    audio_url: str
    audio_type: str = "audio/mpeg"
    audio_bytes: int = 0
    duration_sec: int = 0
    guid: str = ""
    published_at: str = ""


class FeedResponse(BaseModel):
    podcast: PodcastResponse
    episodes: list[EpisodeResponse]


class JobEventResponse(BaseModel):
    id: int
    stage: JobStage
    status: JobStatus
    message: str = ""
    created_at: str


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    stage: JobStage
    title: str = ""
    urls: list[str]
    result: GenerateResponse | None = None
    error: str = ""
    events: list[JobEventResponse] | None = None
    created_at: str
    updated_at: str
    started_at: str = ""
    finished_at: str = ""
