from piratepod_core.logging import get_logger

from .schemas import GenerateRequest, GenerateResponse

log = get_logger(__name__)


def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    log.info("orchestrate.stub", url=str(req.url), title=req.title)
    return GenerateResponse(
        status="stub",
        url=str(req.url),
        title=req.title,
    )
