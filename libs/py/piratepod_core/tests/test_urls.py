from piratepod_core.urls import ensure_url_scheme


def test_ensure_url_scheme_adds_default_scheme() -> None:
    assert ensure_url_scheme("example.com") == "https://example.com"


def test_ensure_url_scheme_keeps_explicit_scheme() -> None:
    assert ensure_url_scheme("http://example.com") == "http://example.com"


def test_ensure_url_scheme_ignores_non_strings() -> None:
    assert ensure_url_scheme(None) is None
