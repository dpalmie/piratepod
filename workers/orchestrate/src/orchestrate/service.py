import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from piratepod_core.logging import get_logger

from .config import AUDIOGEN_URL, HTTP_TIMEOUT, INGEST_URL, SCRIPTGEN_URL
from .schemas import AudioResponse, GenerateRequest, GenerateResponse, IngestResponse

log = get_logger(__name__)


async def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    url = str(req.url)
    log.info("orchestrate.start", url=url, title=req.title)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        ingest = await _ingest(client, url)
        title = req.title or ingest.title
        script = await _scriptgen(client, ingest.markdown, title)
        audio = await _audiogen(client, script, title)

    log.info(
        "orchestrate.done",
        url=url,
        script_chars=len(script),
        audio_path=audio.audio_path,
    )
    return GenerateResponse(
        url=ingest.url,
        title=title,
        markdown=ingest.markdown,
        script=script,
        audio_path=audio.audio_path,
        audio_format=audio.audio_format,
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


async def _audiogen(
    client: httpx.AsyncClient, script: str, title: str
) -> AudioResponse:
    try:
        resp = await client.post(
            f"{AUDIOGEN_URL}/audiogen/audio",
            json={"script": script, "title": title},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"audiogen failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"audiogen unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "audiogen returned invalid json") from e
    try:
        return AudioResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "audiogen returned malformed response") from e
