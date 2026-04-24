import pytest
import respx
from httpx import AsyncClient, Response


@pytest.mark.parametrize("input_url", ["example.com", "https://example.com"])
async def test_ingest_url_accepts_with_or_without_scheme(
    client: AsyncClient,
    jina_mock: respx.MockRouter,
    jina_reader_url: str,
    input_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JINA_API_KEY", "test-key")
    expected_outbound = f"{jina_reader_url}https://example.com/"
    route = jina_mock.get(expected_outbound).respond(200, text="# Example\nbody")

    resp = await client.post("/ingest/url", json={"url": input_url})

    assert resp.status_code == 200, resp.text
    assert resp.text == "# Example\nbody"
    assert route.called and route.call_count == 1
    sent = route.calls.last.request
    assert sent.headers.get("authorization") == "Bearer test-key"


async def test_ingest_url_omits_auth_when_no_key(
    client: AsyncClient,
    jina_mock: respx.MockRouter,
    jina_reader_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    route = jina_mock.get(f"{jina_reader_url}https://example.com/").respond(
        200, text="ok"
    )

    resp = await client.post("/ingest/url", json={"url": "example.com"})

    assert resp.status_code == 200
    assert "authorization" not in route.calls.last.request.headers


async def test_ingest_url_surfaces_upstream_error(
    client: AsyncClient,
    jina_mock: respx.MockRouter,
    jina_reader_url: str,
) -> None:
    jina_mock.get(f"{jina_reader_url}https://example.com/").mock(
        return_value=Response(503, text="upstream down")
    )

    resp = await client.post("/ingest/url", json={"url": "example.com"})

    assert resp.status_code == 502
    assert "503" in resp.json()["detail"]


async def test_ingest_url_rejects_invalid_url(client: AsyncClient) -> None:
    resp = await client.post("/ingest/url", json={"url": "not a url"})
    assert resp.status_code == 422
