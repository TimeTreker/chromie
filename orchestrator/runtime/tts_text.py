from __future__ import annotations


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
