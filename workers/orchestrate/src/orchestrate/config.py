import os

AUDIOGEN_URL = os.getenv("AUDIOGEN_URL", "http://localhost:8004")
INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8001")
RSS_URL = os.getenv("RSS_URL", "http://localhost:8080")
SCRIPTGEN_URL = os.getenv("SCRIPTGEN_URL", "http://localhost:8002")
HTTP_TIMEOUT = float(os.getenv("ORCHESTRATE_HTTP_TIMEOUT", "60"))
ORCHESTRATE_SQLITE_PATH = os.getenv(
    "ORCHESTRATE_SQLITE_PATH",
    ".piratepod/orchestrate.db",
)
ORCHESTRATE_POLL_INTERVAL = float(os.getenv("ORCHESTRATE_POLL_INTERVAL", "1"))

DEFAULT_PODCAST_AUTHOR = os.getenv("PIRATEPOD_DEFAULT_AUTHOR", "")
DEFAULT_PODCAST_DESCRIPTION = os.getenv(
    "PIRATEPOD_DEFAULT_DESCRIPTION",
    "Generated episodes from PiratePod",
)
DEFAULT_PODCAST_LANGUAGE = os.getenv("PIRATEPOD_DEFAULT_LANGUAGE", "en")
DEFAULT_PODCAST_TITLE = os.getenv("PIRATEPOD_DEFAULT_TITLE", "PiratePod")
