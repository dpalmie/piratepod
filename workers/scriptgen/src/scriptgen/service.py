from piratepod_core.logging import get_logger

from .schemas import ScriptRequest, ScriptResponse

log = get_logger(__name__)


def generate_script(req: ScriptRequest) -> ScriptResponse:
    log.info("scriptgen.passthrough", title=req.title, input_chars=len(req.markdown))
    return ScriptResponse(script=req.markdown)
