from fastapi import FastAPI

from .logging import configure_logging


def make_app(title: str) -> FastAPI:
    configure_logging()
    app = FastAPI(title=title)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
