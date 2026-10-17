from __future__ import annotations

from typing import Any


def ends_with_tts_sentence_boundary(text: str) -> bool:
    stripped = text.rstrip()
    while stripped and stripped[-1] in "\"'”’)]}」』":
        stripped = stripped[:-1].rstrip()
    return bool(stripped and stripped[-1] in ".!?。！？")


def ends_with_tts_natural_boundary(text: str) -> bool:
    stripped = text.rstrip()
    while stripped and stripped[-1] in "\"'”’)]}」』":
        stripped = stripped[:-1].rstrip()
    return bool(stripped and stripped[-1] in ".!?。！？,，、;；:：")


def split_tts_sentence_units(text: str) -> list[str]:
    end_chars = ".!?。！？"
    closing_chars = "\"'”’)]}」』"
    units: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        if text[i] in end_chars:
            sentence_mark = text[i]
            end = i + 1
            while end < len(text) and text[end] in closing_chars:
                end += 1
            if end == len(text) or text[end].isspace() or sentence_mark in "。！？":
                unit = text[start:end].strip()
                if unit:
                    units.append(unit)
                start = end
                while start < len(text) and text[start].isspace():
                    start += 1
                i = start
                continue
        i += 1
    tail = text[start:].strip()
    if tail:
        units.append(tail)
    return units or [text]


def split_tts_clause_units(
    text: str,
    *,
    min_chars: int,
    trigger_chars: int,
) -> list[str]:
    if len(text) <= trigger_chars:
        return [text]

    split_chars = ",，、;；:："
    opening_quotes = {"“": "”", "「": "」", "『": "』"}
    closing_quotes = {"”", "」", "』"}
    quote_stack: list[str] = []
    in_plain_quote = False
    units: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            in_plain_quote = not in_plain_quote
        elif char in opening_quotes:
            quote_stack.append(opening_quotes[char])
        elif char in closing_quotes and quote_stack and char == quote_stack[-1]:
            quote_stack.pop()
        elif char in split_chars and not in_plain_quote and not quote_stack:
            end = i + 1
            unit = text[start:end].strip()
            tail = text[end:].strip()
            if len(unit) >= min_chars and len(tail) >= min_chars:
                units.append(unit)
                start = end
                while start < len(text) and text[start].isspace():
                    start += 1
                i = start
                continue
        i += 1

    tail = text[start:].strip()
    if tail:
        units.append(tail)
    return units or [text]


def split_oversized_tts_unit(text: str, hard_limit: int) -> list[str]:
    if len(text) <= hard_limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > hard_limit:
        cut = remaining[:hard_limit]
        cut_points = [
            cut.rfind(sep)
            for sep in (",", "，", "、", ";", "；", ":", "：", " ")
        ]
        cut_at = max(cut_points)
        if cut_at < max(20, hard_limit // 2):
            cut_at = hard_limit
        else:
            cut_at += 1
        chunk = remaining[:cut_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def should_merge_tts_chunks(
    current: str,
    chunk: str,
    *,
    limit: int,
    hard_limit: int,
    min_chars: int,
) -> bool:
    merged_len = len(current) + 1 + len(chunk)
    if merged_len > hard_limit:
        return False
    if len(current) < min_chars:
        return True
    if len(chunk) < min_chars and merged_len <= limit:
        return True
    if not ends_with_tts_natural_boundary(current) and merged_len <= limit:
        return True
    return False


def split_tts_text(host: Any, text: str) -> list[str]:
    candidate = host.normalize_tts_candidate(text)
    if not host.is_valid_tts_text(candidate):
        return []
    if not getattr(host, "tts_text_chunking_enabled", True):
        return [candidate]
    max_text_chars = max(20, int(getattr(host, "tts_max_text_chars", 220)))
    limit = max(
        20,
        min(
            max_text_chars,
            int(getattr(host, "tts_chunk_chars", getattr(host, "tts_flush_chars", 160))),
        ),
    )
    contains_cjk = any("\u4e00" <= char <= "\u9fff" for char in candidate)
    if contains_cjk:
        limit = min(
            limit,
            max(12, int(getattr(host, "tts_cjk_chunk_chars", 36))),
        )
    first_limit = int(getattr(host, "tts_first_chunk_chars", min(limit, 16)) or 0)
    first_limit = max(4, min(limit, first_limit)) if first_limit > 0 else limit
    hard_limit = min(max_text_chars, limit) if contains_cjk else max_text_chars

    raw_chunks: list[str] = []
    min_chars = max(1, int(getattr(host, "tts_min_chunk_chars", 40)))
    if contains_cjk:
        min_chars = min(
            min_chars,
            max(1, int(getattr(host, "tts_cjk_min_chunk_chars", 8))),
        )
        clause_trigger = max(limit, min_chars * 2)
    else:
        clause_trigger = max(80, min(limit, hard_limit) // 2, min_chars * 3)
    for unit in split_tts_sentence_units(candidate):
        for clause in split_tts_clause_units(
            unit,
            min_chars=min_chars,
            trigger_chars=clause_trigger,
        ):
            raw_chunks.extend(split_oversized_tts_unit(clause, hard_limit))
    if not raw_chunks:
        return [candidate]

    chunks: list[str] = []
    current = ""
    grouped_chunks = raw_chunks
    if (
        first_limit < limit
        and len(raw_chunks) > 1
        and len(raw_chunks[0]) <= first_limit
        and ends_with_tts_sentence_boundary(raw_chunks[0])
    ):
        chunks.append(raw_chunks[0])
        grouped_chunks = raw_chunks[1:]
    for chunk in grouped_chunks:
        merged = f"{current} {chunk}".strip() if current else chunk
        if not current:
            current = chunk
        elif should_merge_tts_chunks(
            current,
            chunk,
            limit=limit,
            hard_limit=hard_limit,
            min_chars=min_chars,
        ):
            current = merged
        else:
            chunks.append(current)
            current = chunk
    if current:
        chunks.append(current)
    return chunks or [candidate]
