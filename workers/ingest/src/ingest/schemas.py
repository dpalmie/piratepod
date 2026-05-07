import re
from typing import Any
from urllib.parse import urljoin, urlparse

from piratepod_core.urls import ensure_url_scheme
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

IMAGE_URL_FIELDS = (
    "image",
    "imageUrl",
    "ogImage",
    "og:image",
    "twitterImage",
    "twitter:image",
    "thumbnail",
    "thumbnailUrl",
)
IMAGE_LIST_FIELD = "images"
NESTED_IMAGE_FIELDS = ("metadata", "meta")
IMAGE_VALUE_FIELDS = ("url", "src", "href")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")


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
    image_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _extract_image_url(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("image_url"):
            return data
        image = _first_image_url(data)
        if image:
            data = {**data, "image_url": image}
        return data


def _first_image_url(data: dict[str, Any]) -> str | None:
    base_url = data.get("url") if isinstance(data.get("url"), str) else ""
    for key in IMAGE_URL_FIELDS:
        value = _coerce_image_value(data.get(key))
        if url := _normalize_image_url(value, base_url):
            return url

    value = _coerce_image_value(data.get(IMAGE_LIST_FIELD))
    if url := _normalize_image_url(value, base_url):
        return url

    for key in NESTED_IMAGE_FIELDS:
        nested = data.get(key)
        if isinstance(nested, dict):
            nested_image = _first_image_url({**nested, "url": base_url})
            if nested_image:
                return nested_image

    content = data.get("content")
    if isinstance(content, str):
        match = MARKDOWN_IMAGE_RE.search(content)
        if match:
            return _normalize_image_url(match.group(1), base_url)
    return None


def _coerce_image_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in IMAGE_VALUE_FIELDS:
            if isinstance(value.get(key), str):
                return value[key]
    if isinstance(value, list):
        for item in value:
            if coerced := _coerce_image_value(item):
                return coerced
    return None


def _normalize_image_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("//"):
        value = "https:" + value
    elif base_url:
        value = urljoin(base_url, value)
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None
