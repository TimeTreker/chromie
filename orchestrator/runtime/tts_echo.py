"""TTS echo detection for ASR transcripts heard during or after playback.

The functions take the VoiceAssistant composition root as ``host`` and read the
spoken text that PlaybackDelivery retained per playback generation.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import unicodedata
from typing import Any


def normalize_echo_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(char for char in normalized if char.isalnum())


def remember_tts_text(host: Any, generation: int, text: str) -> None:
    normalized = host.normalize_tts_candidate(text)
    if not normalized:
        return
    store = host.playback_delivery.tts_text_by_generation
    if not isinstance(store, dict):
        store = {}
        host.playback_delivery.tts_text_by_generation = store
    history = store.setdefault(int(generation), [])
    history.append(normalized)
    # Retain only the current and a few recent generations.  A delayed ASR
    # response may arrive after playback advances, but old dialogue must not
    # accumulate for the lifetime of the process.
    minimum_generation = int(generation) - 3
    for old_generation in list(store):
        if old_generation < minimum_generation:
            store.pop(old_generation, None)


def likely_tts_echo(
    host: Any,
    transcript: str,
    *,
    playback_generation_at_start: int | None,
    started_during_playback: bool = True,
    capture_started_monotonic_ms: float | None = None,
    post_playback_tail_ms: float = 500.0,
) -> tuple[bool, float, float]:
    if playback_generation_at_start is None:
        return False, 0.0, 0.0
    if not started_during_playback:
        playback_state = host.playback_delivery
        last_generation = playback_state.last_completed_playback_generation
        playback_end_ms = playback_state.last_playback_end_monotonic_ms
        if (
            last_generation != int(playback_generation_at_start)
            or playback_end_ms is None
            or capture_started_monotonic_ms is None
            or capture_started_monotonic_ms > playback_end_ms + max(0.0, float(post_playback_tail_ms))
        ):
            return False, 0.0, 0.0
    store = host.playback_delivery.tts_text_by_generation
    if not isinstance(store, dict):
        store = {}
    spoken_parts = store.get(
        int(playback_generation_at_start),
        [],
    )
    transcript_key = normalize_echo_text(transcript)
    part_keys = [
        key
        for part in spoken_parts
        if (key := normalize_echo_text(part))
    ]
    if len(transcript_key) < 2 or not part_keys:
        return False, 0.0, 0.0
    # One retained output recording corresponds to one scheduled TTS order.
    # Compare ASR against each order first so a short replay is not diluted
    # by an entire multi-sentence generation.  Adjacent and whole-generation
    # candidates retain coverage for VAD segments that cross order bounds.
    candidate_keys = list(part_keys)
    candidate_keys.extend(
        left + right
        for left, right in zip(part_keys, part_keys[1:], strict=False)
    )
    candidate_keys.append("".join(part_keys))

    best_ratio = 0.0
    best_coverage = 0.0
    best_strength = -1.0
    for spoken_key in dict.fromkeys(candidate_keys):
        if transcript_key in spoken_key:
            return True, 1.0, 1.0
        matcher = SequenceMatcher(
            None,
            transcript_key,
            spoken_key,
            autojunk=False,
        )
        ratio = float(matcher.ratio())
        longest = max(
            (block.size for block in matcher.get_matching_blocks()),
            default=0,
        )
        transcript_coverage = float(
            longest / max(1, len(transcript_key))
        )
        strength = max(ratio / 0.78, transcript_coverage / 0.88)
        if strength > best_strength:
            best_ratio = ratio
            best_coverage = transcript_coverage
            best_strength = strength
    if started_during_playback:
        likely = bool(
            best_ratio >= 0.78
            or (best_coverage >= 0.88 and len(transcript_key) >= 6)
        )
    else:
        # Outside active playback require a much stronger textual match.
        # This catches speaker/acoustic tails without swallowing an ordinary
        # person who happens to respond with vaguely similar wording.
        likely = bool(
            best_ratio >= 0.94
            or (best_coverage >= 0.98 and len(transcript_key) >= 6)
        )
    return likely, best_ratio, best_coverage
