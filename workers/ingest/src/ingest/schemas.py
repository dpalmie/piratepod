from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class UrlRequest(BaseModel):
    url: HttpUrl

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, v: Any) -> Any:
        if isinstance(v, str) and "://" not in v:
            return f"https://{v}"
        return v


class UrlResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    url: str
    published_time: str | None = Field(default=None, alias="publishedTime")
    markdown: str = Field(alias="content")
