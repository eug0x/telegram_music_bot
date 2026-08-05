# core/utils/text.py

import re
from typing import Optional

_BRACKETS_RE = re.compile(r'\[.*?\]|\(.*?\)|\{.*?\}')
_NON_WORD_RE = re.compile(r'[^\w\s]')
_MULTI_SPACE_RE = re.compile(r'\s+')

_NOISE_WORDS = (
    r'm/v', r'official', r'video', r'audio', r'hd', r'hq',
    r'remastered', r'version', r'lyrics',
)
_NOISE_WORDS_RE = re.compile(r'\b(?:' + '|'.join(_NOISE_WORDS) + r')\b')


def normalize_text(text: Optional[str], strip_noise_words: bool = False) -> str:
    if not text:
        return ""
    normalized = text.lower()
    normalized = _BRACKETS_RE.sub(' ', normalized)
    if strip_noise_words:
        normalized = _NOISE_WORDS_RE.sub(' ', normalized)
    normalized = _NON_WORD_RE.sub(' ', normalized)
    normalized = _MULTI_SPACE_RE.sub(' ', normalized).strip()
    return normalized


def escape_like_pattern(value: str, escape_char: str = '\\') -> str:
    if not value:
        return ""
    value = value.replace(escape_char, escape_char * 2)
    value = value.replace('%', f'{escape_char}%')
    value = value.replace('_', f'{escape_char}_')
    return value
