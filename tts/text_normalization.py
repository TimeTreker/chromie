"""Speech-text cleanup shared by the Host and the TTS service.

Standard library only: the TTS image copies this file beside ``server.py``,
and the Host imports it as ``tts.text_normalization``.
"""

from __future__ import annotations

import re

_MARKUP_RE = re.compile(r"[*_#>\[\]{}|]+")
_WHITESPACE_RE = re.compile(r"\s+")
_LIST_NUMBER_RE = re.compile(r"\d+[\.)]?")


def strip_speech_markup(text: str | None) -> str:
    """Remove Markdown-style markup and collapse whitespace."""

    text = (text or "").strip()
    text = text.replace("```", " ").replace("`", " ").replace("**", " ")
    text = _MARKUP_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def has_speakable_content(text: str, *, min_chars: int) -> bool:
    """Return whether cleaned ``text`` is worth synthesizing."""

    if len(text) < min_chars:
        return False
    if _LIST_NUMBER_RE.fullmatch(text):
        return False
    return any(ch.isalnum() or "一" <= ch <= "鿿" for ch in text)
