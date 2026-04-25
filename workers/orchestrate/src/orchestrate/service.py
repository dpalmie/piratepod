import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from piratepod_core.logging import get_logger

from .config import HTTP_TIMEOUT, INGEST_URL, SCRIPTGEN_URL
from .schemas import GenerateRequest, GenerateResponse, IngestResponse

log = get_logger(__name__)


async def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    url = str(req.url)
    log.info("orchestrate.start", url=url, title=req.title)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        ingest = await _ingest(client, url)
        title = req.title or ingest.title
        script = await _scriptgen(client, ingest.markdown, title)

    log.info("orchestrate.done", url=url, script_chars=len(script))
    return GenerateResponse(
        url=ingest.url,
        title=title,
        markdown=ingest.markdown,
        script=script,
    )


async def _ingest(client: httpx.AsyncClient, url: str) -> IngestResponse:
    try:
        resp = await client.post(f"{INGEST_URL}/ingest/url", json={"url": url})
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"ingest failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"ingest unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "ingest returned invalid json") from e
    try:
        return IngestResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "ingest returned malformed response") from e


async def _scriptgen(client: httpx.AsyncClient, markdown: str, title: str) -> str:
    try:
        resp = await client.post(
            f"{SCRIPTGEN_URL}/scriptgen/script",
            json={"markdown": markdown, "title": title},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"scriptgen failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"scriptgen unreachable: {e}") from e
    return resp.json()["script"]
