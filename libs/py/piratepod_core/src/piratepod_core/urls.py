from typing import Any


def ensure_url_scheme(value: Any, default_scheme: str = "https") -> Any:
    if isinstance(value, str) and "://" not in value:
        return f"{default_scheme}://{value}"
    return value
