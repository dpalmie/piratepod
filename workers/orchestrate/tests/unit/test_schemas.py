import pytest
from pydantic import ValidationError

from orchestrate.schemas import GenerateRequest


def test_generate_request_adds_https_scheme() -> None:
    req = GenerateRequest(urls=["example.com"])

    assert [str(url) for url in req.urls] == ["https://example.com/"]


def test_generate_request_keeps_explicit_scheme() -> None:
    req = GenerateRequest(urls=["http://example.com"])

    assert [str(url) for url in req.urls] == ["http://example.com/"]


def test_generate_request_rejects_old_url_shape() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(url="example.com")  # type: ignore[call-arg]


def test_generate_request_requires_at_least_one_url() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(urls=[])
