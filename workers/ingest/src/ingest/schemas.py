from typing import Any

from piratepod_core.urls import ensure_url_scheme
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class UrlRequest(BaseModel):
    url: HttpUrl

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, v: Any) -> Any:
        return ensure_url_scheme(v)


class UrlResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    url: str
    published_time: str | None = Field(default=None, alias="publishedTime")
    markdown: str = Field(alias="content")
