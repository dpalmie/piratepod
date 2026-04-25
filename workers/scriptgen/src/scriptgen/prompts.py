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
    Write the main podcast introduction for this combined episode.
    Set context and tee up the stories in 2-4 sentences.
    Return JSON exactly like: {"intro":"..."}
    """
)

SEGMENT_PROMPT = clean_prompt(
    """
    Write one podcast story segment from this source.
    Use a short setup, a clear main narration, and a brief wrap.
    Keep it concise and spoken-word friendly.
    Return JSON exactly like: {"title":"...","intro":"...","main":"...","outro":"..."}
    """
)

OUTRO_PROMPT = clean_prompt(
    """
    Write the main podcast conclusion for this combined episode.
    Tie the sources together, briefly summarize the takeaway, and close the episode.
    Return JSON exactly like: {"outro":"..."}
    """
)

SOURCE_CONTEXT_TEMPLATE = clean_prompt(
    """
    SOURCE {index}:

    TITLE:
    {title}

    URL:
    {url}

    ARTICLE:
    {article}
    """
)

EPISODE_CONTEXT_TEMPLATE = clean_prompt(
    """
    EPISODE TITLE:
    {title}

    SOURCES:
    {sources}
    """
)


def intro_prompt(title: str, sources: str) -> str:
    return f"{INTRO_PROMPT}\n\n{episode_context(title, sources)}"


def segment_prompt(title: str, source: str) -> str:
    return f"{SEGMENT_PROMPT}\n\n{episode_context(title, source)}"


def outro_prompt(title: str, sources: str) -> str:
    return f"{OUTRO_PROMPT}\n\n{episode_context(title, sources)}"


def source_context(index: int, title: str, url: str, article: str) -> str:
    return SOURCE_CONTEXT_TEMPLATE.format(
        index=index,
        title=title,
        url=url,
        article=article,
    )


def sources_context(sources: list[tuple[str, str, str]]) -> str:
    return "\n\n---\n\n".join(
        source_context(index, title, url, article)
        for index, (title, url, article) in enumerate(sources, start=1)
    )


def episode_context(title: str, sources: str) -> str:
    return EPISODE_CONTEXT_TEMPLATE.format(title=title, sources=sources)
