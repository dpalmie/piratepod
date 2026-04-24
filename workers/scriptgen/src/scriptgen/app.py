from piratepod_core import make_app

from .routes import router

app = make_app("piratepod-scriptgen")
app.include_router(router)
