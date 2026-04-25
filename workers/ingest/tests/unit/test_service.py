import pytest
from pydantic import ValidationError

from ingest.schemas import UrlResponse


def test_url_response_maps_jina_json_data() -> None:
    result = UrlResponse.model_validate(
        {
            "title": "Example Domain",
            "url": "https://example.com/",
            "content": "This domain is for use in documentation examples.\n",
            "publishedTime": "Sat, 18 Apr 2026 00:49:31 GMT",
        }
    )

    assert result.title == "Example Domain"
    assert result.url == "https://example.com/"
    assert result.published_time == "Sat, 18 Apr 2026 00:49:31 GMT"
    assert result.markdown == "This domain is for use in documentation examples.\n"


def test_url_response_accepts_our_api_field_names() -> None:
    result = UrlResponse.model_validate(
        {
            "title": "Example Domain",
            "url": "https://example.com/",
            "markdown": "Body",
            "published_time": "Sat, 18 Apr 2026 00:49:31 GMT",
        }
    )

    assert result.markdown == "Body"
    assert result.published_time == "Sat, 18 Apr 2026 00:49:31 GMT"


def test_url_response_requires_title() -> None:
    with pytest.raises(ValidationError) as exc:
        UrlResponse.model_validate(
            {"url": "https://example.com/", "content": "Body without title"}
        )

    assert "title" in str(exc.value)


def test_url_response_requires_content() -> None:
    with pytest.raises(ValidationError) as exc:
        UrlResponse.model_validate(
            {"title": "Example Domain", "url": "https://example.com/"}
        )

    assert "content" in str(exc.value)
