from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, HttpUrl

from .fetcher import fetch_url

router = APIRouter()


class UrlRequest(BaseModel):
    url: HttpUrl


@router.post("/ingest/url", response_class=PlainTextResponse)
async def ingest_url(req: UrlRequest) -> str:
    return await fetch_url(str(req.url))
