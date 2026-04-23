from piratepod_core.app import make_app

from .routes import router

app = make_app("piratepod-ingest")
app.include_router(router)
