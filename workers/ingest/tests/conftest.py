import os
from collections.abc import AsyncIterator, Iterator

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from ingest.app import app
from ingest.config import JINA_READER


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def jina_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def jina_reader_url() -> str:
    return JINA_READER


@pytest.fixture
def require_live() -> None:
    """Skip live tests unless explicitly opted in via RUN_LIVE_TESTS=1.

    Jina Reader's free tier (20 RPM by IP, no API key) is sufficient, so we
    do not require JINA_API_KEY.
    """
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_TESTS=1 to run live tests")
