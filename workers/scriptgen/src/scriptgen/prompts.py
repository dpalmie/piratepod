from piratepod_core.prompts import clean_prompt


SYSTEM_PROMPT = clean_prompt(
    """
    You write concise podcast scripts for spoken audio.
    Use only facts from the provided article. Do not invent details.
    Write in a natural single-host voice. Avoid markdown links and citations.
    Return valid JSON only, with no commentary.
    """
)

INTRO_PROMPT = clean_prompt(
    """
    Write the main podcast introduction for this episode.
    Set context and tee up the story in 2-4 sentences.
    Return JSON exactly like: {"intro":"..."}
    """
)

SEGMENT_PROMPT = clean_prompt(
    """
    Write one podcast story segment from this article.
    Use a short setup, a clear main narration, and a brief wrap.
    Keep it concise and spoken-word friendly.
    Return JSON exactly like: {"title":"...","intro":"...","main":"...","outro":"..."}
    """
)

OUTRO_PROMPT = clean_prompt(
    """
    Write the main podcast conclusion for this episode.
    Briefly summarize the takeaway and close the episode.
    Return JSON exactly like: {"outro":"..."}
    """
)

ARTICLE_CONTEXT_TEMPLATE = clean_prompt(
    """
    TITLE:
    {title}

    ARTICLE:
    {article}
    """
)


def intro_prompt(title: str, article: str) -> str:
    return f"{INTRO_PROMPT}\n\n{article_context(title, article)}"


def segment_prompt(title: str, article: str) -> str:
    return f"{SEGMENT_PROMPT}\n\n{article_context(title, article)}"


def outro_prompt(title: str, article: str) -> str:
    return f"{OUTRO_PROMPT}\n\n{article_context(title, article)}"


def article_context(title: str, article: str) -> str:
    return ARTICLE_CONTEXT_TEMPLATE.format(title=title, article=article)
