"""Live integration tests against the real Jina Reader.

Opt-in via RUN_LIVE_TESTS=1. Jina's free tier (20 RPM by IP) is sufficient,
so JINA_API_KEY is not required. example.com is the canonical stable test
page (IANA-reserved); its body always contains the phrase "Example Domain".
"""

import pytest
from httpx import ASGITransport, AsyncClient

from ingest.app import app


@pytest.mark.parametrize("input_url", ["example.com", "https://example.com"])
async def test_ingest_url_live_jina(require_live: None, input_url: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", timeout=60.0
    ) as client:
        resp = await client.post("/ingest/url", json={"url": input_url})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["title"] == "Example Domain"
    assert "This domain is for use" in data["markdown"], data["markdown"][:500]
