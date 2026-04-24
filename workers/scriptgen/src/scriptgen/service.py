from piratepod_core.logging import get_logger

from .schemas import ScriptRequest, ScriptResponse

log = get_logger(__name__)

CANNED = """Welcome to Piratepod. Today's topic: {title}.

Here's a summary of what we found:
{preview}

That's all for this episode. Thanks for listening."""


def generate_script(req: ScriptRequest) -> ScriptResponse:
    title = req.title or "this topic"
    preview = req.markdown[:300] + ("..." if len(req.markdown) > 300 else "")
    log.info("scriptgen.stub", title=title, input_chars=len(req.markdown))
    return ScriptResponse(script=CANNED.format(title=title, preview=preview))
