"""Lossless literal-text segmentation for additional punctuation pauses.

Heuristics, not NLP: known abbreviations suppress a single period even at EOF;
uppercase initials before uppercase words and numbers before lowercase words
are treated as nonterminal. Unknown abbreviations and ambiguous sentence-final
initials/numbers cannot always be disambiguated. Each input chunk stands alone.
XML entities/tags are never decoded, parsed, escaped or normalized.
"""
import re
try:
    from .i18n import _
except ImportError:
    from i18n import _

_ABBREVIATIONS = frozenset(('г', 'ул', 'д', 'стр', 'рис', 'им', 'т.д', 'т.п', 'т.е',
                            'mr', 'mrs', 'dr', 'e.g', 'i.e', 'etc'))
_TOKEN = re.compile(r'[\w.]+$', re.UNICODE)


def _protected_period(text, index):
    match = _TOKEN.search(text[:index])
    token = match.group() if match else ''
    if token.casefold() == 'т' and re.match(r'\s+[дпе]\.', text[index + 1:], re.I):
        return True
    if re.search(r'(?<!\w)т\.\s+[дпе]\.$', text[:index + 1], re.I):
        return True
    if token.casefold() in _ABBREVIATIONS:
        return True
    following = text[index + 1:].lstrip()
    if not following:
        return False
    return (len(token) == 1 and token.isalpha() and token.isupper()
            and following[0].isupper()) or (token.isdigit() and following[0].islower())



def validate_pauses(comma_ms=0, sentence_ms=0) -> None:
    """Reject booleans, non-integers and out-of-range millisecond values."""
    for value in (comma_ms, sentence_ms):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2000:
            raise ValueError(_('Пауза должна быть целым числом от 0 до 2000 мс.'))


def pause_segments(text: str, comma_ms=0, sentence_ms=0) -> list[tuple[str, str | int]]:
    """Return literal text and additional pause durations; preserve all characters."""
    validate_pauses(comma_ms, sentence_ms)
    if not comma_ms and not sentence_ms:
        return [('text', text)]
    segments = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        end = index + 1
        duration = 0
        numeric = index > 0 and end < len(text) and text[index - 1].isdigit() and text[end].isdigit()
        if char == ',' and comma_ms and not numeric:
            duration = comma_ms
        elif char in '.!?…' and sentence_ms:
            while end < len(text) and text[end] in '.!?…':
                end += 1
            protected = end == index + 1 and char == '.' and _protected_period(text, index)
            boundary = end == len(text) or text[end].isspace() or text[end] in '\"\'»”’)]}'
            while end < len(text) and text[end] in '\"\'»”’)]}':
                end += 1
            if boundary and not protected:
                duration = sentence_ms
        if duration:
            segments.extend([('text', text[start:end]), ('pause', duration)])
            start = end
        index = end
    if start < len(text) or not segments:
        segments.append(('text', text[start:]))
    return segments
