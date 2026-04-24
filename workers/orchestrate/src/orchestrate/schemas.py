from pydantic import BaseModel, HttpUrl


class GenerateRequest(BaseModel):
    url: HttpUrl
    title: str | None = None


class GenerateResponse(BaseModel):
    url: str
    title: str | None = None
    markdown: str
    script: str
