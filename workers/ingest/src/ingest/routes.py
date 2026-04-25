from fastapi import APIRouter

from .schemas import UrlRequest, UrlResponse
from .service import fetch_url

router = APIRouter()


@router.post("/ingest/url", response_model=UrlResponse, response_model_by_alias=False)
async def ingest_url(req: UrlRequest) -> UrlResponse:
    return await fetch_url(str(req.url))
