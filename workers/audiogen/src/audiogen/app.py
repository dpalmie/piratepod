from piratepod_core import make_app

from .routes import router

app = make_app("piratepod-audiogen")
app.include_router(router)
