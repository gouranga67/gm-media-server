import re


def _caption_phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    words = phrase.split()
    if not words:
        return None
    expression = r"\s+".join(re.escape(word) for word in words)
    if words[0][0].isalnum() or words[0][0] == "_":
        expression = r"(?<!\w)" + expression
    if words[-1][-1].isalnum() or words[-1][-1] == "_":
        expression += r"(?!\w)"
    return re.compile(expression, re.IGNORECASE)


def caption_phrase_exists(text: str, phrase: str) -> bool:
    pattern = _caption_phrase_pattern(phrase)
    return pattern is not None and pattern.search(text) is not None


def replace_caption_phrase(text: str, original: str, replacement: str) -> str:
    pattern = _caption_phrase_pattern(original)
    if pattern is None:
        return text
    return pattern.sub(lambda _match: replacement, text)
