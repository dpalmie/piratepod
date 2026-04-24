from typing import Any

from pydantic import BaseModel, HttpUrl, field_validator


class UrlRequest(BaseModel):
    url: HttpUrl

    @field_validator("url", mode="before")
    @classmethod
    def _ensure_scheme(cls, v: Any) -> Any:
        if isinstance(v, str) and "://" not in v:
            return f"https://{v}"
        return v
