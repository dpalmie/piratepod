from typing import Any

from fastapi import FastAPI

from .logging import configure_logging


def make_app(title: str, **kwargs: Any) -> FastAPI:
    configure_logging()
    app = FastAPI(title=title, **kwargs)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
