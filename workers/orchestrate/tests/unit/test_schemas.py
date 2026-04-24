from orchestrate.schemas import GenerateRequest


def test_generate_request_adds_https_scheme() -> None:
    req = GenerateRequest(url="example.com")

    assert str(req.url) == "https://example.com/"


def test_generate_request_keeps_explicit_scheme() -> None:
    req = GenerateRequest(url="http://example.com")

    assert str(req.url) == "http://example.com/"
