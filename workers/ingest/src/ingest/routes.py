from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .schemas import UrlRequest
from .service import fetch_url

router = APIRouter()


@router.post("/ingest/url", response_class=PlainTextResponse)
async def ingest_url(req: UrlRequest) -> str:
    return await fetch_url(str(req.url))
