from textwrap import dedent


def clean_prompt(text: str) -> str:
    return dedent(text).strip()
