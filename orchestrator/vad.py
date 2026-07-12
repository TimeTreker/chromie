from __future__ import annotations

import collections
import logging

try:
    import webrtcvad
except Exception:  # pragma: no cover
    webrtcvad = None

logger = logging.getLogger(__name__)


class VAD:
    """WebRTC VAD wrapper for PCM16 mono audio frames."""

    def __init__(
        self,
        mode: int = 3,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        silence_timeout_ms: int = 650,
        pre_roll_ms: int = 300,
        max_utterance_ms: int = 20000,
    ):
        self.mode = int(mode)
        self.sample_rate = int(sample_rate)
        self.frame_duration_ms = int(frame_duration_ms)
        self.silence_timeout_ms = int(silence_timeout_ms)
        self.pre_roll_ms = int(pre_roll_ms)
        self.max_utterance_ms = max(0, int(max_utterance_ms))
        self.vad = webrtcvad.Vad(self.mode) if webrtcvad else None
        self.in_speech = False
        self.silence_ms = 0
        self.current = bytearray()
        self.last_end_reason: str | None = None
        self.pre_roll_frames = collections.deque(
            maxlen=max(1, int(self.pre_roll_ms / max(1, self.frame_duration_ms)))
        )

    def reset(self) -> None:
        self.in_speech = False
        self.silence_ms = 0
        self.current.clear()
        self.pre_roll_frames.clear()

    def _is_speech(self, frame: bytes) -> bool:
        if not frame:
            return False
        if self.vad is None:
            # Fallback: non-zero energy heuristic if webrtcvad is unavailable.
            return any(b != 0 for b in frame)
        try:
            return bool(self.vad.is_speech(frame, self.sample_rate))
        except Exception as exc:
            logger.debug("VAD frame error: %s", exc)
            return False

    def process_chunk(self, frame: bytes) -> tuple[bool, bool, bytes | None]:
        self.last_end_reason = None
        speech = self._is_speech(frame)
        started = False
        ended = False
        audio: bytes | None = None

        if not self.in_speech:
            self.pre_roll_frames.append(frame)
            if speech:
                self.in_speech = True
                started = True
                self.silence_ms = 0
                for prev in self.pre_roll_frames:
                    self.current.extend(prev)
                self.pre_roll_frames.clear()
            return started, ended, audio

        self.current.extend(frame)
        if self.max_utterance_ms > 0:
            current_ms = (
                len(self.current) / max(1, self.sample_rate * 2) * 1000.0
            )
            if current_ms >= self.max_utterance_ms:
                ended = True
                audio = bytes(self.current)
                self.reset()
                self.last_end_reason = "max_duration"
                return started, ended, audio

        if speech:
            self.silence_ms = 0
            return started, ended, audio

        self.silence_ms += self.frame_duration_ms
        if self.silence_ms >= self.silence_timeout_ms:
            ended = True
            audio = bytes(self.current)
            self.reset()
            self.last_end_reason = "silence"
        return started, ended, audio
