import os

AUDIOGEN_URL = os.getenv("AUDIOGEN_URL", "http://localhost:8004")
INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8001")
SCRIPTGEN_URL = os.getenv("SCRIPTGEN_URL", "http://localhost:8002")
HTTP_TIMEOUT = float(os.getenv("ORCHESTRATE_HTTP_TIMEOUT", "60"))
