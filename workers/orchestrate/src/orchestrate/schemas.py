from pydantic import BaseModel, HttpUrl


class GenerateRequest(BaseModel):
    url: HttpUrl
    title: str | None = None


class GenerateResponse(BaseModel):
    status: str
    url: str
    title: str | None = None
