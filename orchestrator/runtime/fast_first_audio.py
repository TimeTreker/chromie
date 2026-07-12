from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import websockets

logger = logging.getLogger("chromie-orchestrator.fast-first-audio")


@dataclass(frozen=True)
class FastFirstCue:
    purpose: str
    language: str
    text: str


@dataclass(frozen=True)
class CachedFastFirstAudio:
    purpose: str
    language: str
    text: str
    pcm16: bytes
    sample_rate: int
    path: Path


DEFAULT_FAST_FIRST_CUES: tuple[FastFirstCue, ...] = (
    FastFirstCue("checking", "en", "One moment."),
    FastFirstCue("thinking", "en", "Let me think."),
    FastFirstCue("planning", "en", "Let me check that."),
    FastFirstCue("checking", "zh", "稍等一下。"),
    FastFirstCue("thinking", "zh", "我想一下。"),
    FastFirstCue("planning", "zh", "我先确认一下。"),
)


class FastFirstAudioCache:
    """Startup-primed, in-memory PCM cache for low-commitment acknowledgements.

    The cache is presentation infrastructure only. Semantic routing decides
    whether a turn is tool work, deeper reasoning, or guarded action planning;
    this class merely maps that already-selected state to a generic, truthful
    acknowledgement and avoids a realtime generative-TTS request.
    """

    CACHE_VERSION = "v1"

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        enabled: bool = True,
        prime_on_startup: bool = True,
        request_timeout_s: float = 120.0,
        cues: Iterable[FastFirstCue] = DEFAULT_FAST_FIRST_CUES,
    ) -> None:
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.enabled = bool(enabled)
        self.prime_on_startup = bool(prime_on_startup)
        self.request_timeout_s = max(1.0, float(request_timeout_s))
        self.cues = tuple(cues)
        self._audio: dict[tuple[str, str], CachedFastFirstAudio] = {}
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_language(language: str | None, text: str = "") -> str:
        normalized = (language or "").strip().lower()
        if normalized.startswith("zh"):
            return "zh"
        if any("\u4e00" <= ch <= "\u9fff" for ch in text or ""):
            return "zh"
        return "en"

    @staticmethod
    def purpose_for_route(route: str) -> str | None:
        normalized = (route or "").strip().lower()
        if normalized == "tool":
            return "checking"
        if normalized == "deep_thought":
            return "thinking"
        if normalized in {"robot_action", "memory"}:
            return "planning"
        return None

    def cue_for(self, *, route: str, language: str | None, user_text: str = "") -> FastFirstCue | None:
        purpose = self.purpose_for_route(route)
        if purpose is None:
            return None
        lang = self.normalize_language(language, user_text)
        for cue in self.cues:
            if cue.purpose == purpose and cue.language == lang:
                return cue
        return None

    def _cache_path(self, cue: FastFirstCue, speaker_id: str) -> Path:
        digest = hashlib.sha256(
            f"{self.CACHE_VERSION}\0{speaker_id}\0{cue.language}\0{cue.purpose}\0{cue.text}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        safe_speaker = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in speaker_id)[:48]
        return self.cache_dir / f"{cue.language}-{cue.purpose}-{safe_speaker}-{digest}.wav"

    @staticmethod
    def _read_wav(path: Path, cue: FastFirstCue) -> CachedFastFirstAudio | None:
        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                    logger.warning("Ignoring incompatible fast-first cache file: %s", path)
                    return None
                sample_rate = int(wav.getframerate())
                pcm16 = wav.readframes(wav.getnframes())
        except (OSError, wave.Error) as exc:
            logger.warning("Failed to read fast-first cache file %s: %s", path, exc)
            return None
        if not pcm16 or sample_rate <= 0:
            return None
        return CachedFastFirstAudio(
            purpose=cue.purpose,
            language=cue.language,
            text=cue.text,
            pcm16=pcm16,
            sample_rate=sample_rate,
            path=path,
        )

    @staticmethod
    def _write_wav_atomic(path: Path, *, pcm16: bytes, sample_rate: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        os.close(fd)
        temp_path = Path(raw_temp)
        try:
            with wave.open(str(temp_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(int(sample_rate))
                wav.writeframes(pcm16)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)

    def load_existing(self, *, speaker_id: str) -> int:
        if not self.enabled:
            return 0
        loaded = 0
        for cue in self.cues:
            path = self._cache_path(cue, speaker_id)
            if not path.exists():
                continue
            audio = self._read_wav(path, cue)
            if audio is None:
                continue
            self._audio[(cue.purpose, cue.language)] = audio
            loaded += 1
        return loaded

    def get(self, *, route: str, language: str | None, user_text: str = "") -> CachedFastFirstAudio | None:
        if not self.enabled:
            return None
        cue = self.cue_for(route=route, language=language, user_text=user_text)
        if cue is None:
            return None
        return self._audio.get((cue.purpose, cue.language))

    async def _synthesize_cue(
        self,
        cue: FastFirstCue,
        *,
        tts_url: str,
        speaker_id: str,
    ) -> tuple[bytes, int]:
        request_id = "fast-first-cache-" + hashlib.sha256(cue.text.encode("utf-8")).hexdigest()[:12]

        async def run() -> tuple[bytes, int]:
            async with websockets.connect(
                tts_url,
                max_size=10**7,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "synthesize_stream",
                            "text": cue.text,
                            "speaker_id": speaker_id,
                            "request_id": request_id,
                        },
                        ensure_ascii=False,
                    )
                )
                pcm = bytearray()
                sample_rate = 44100
                async for message in ws:
                    if isinstance(message, bytes):
                        pcm.extend(message)
                        continue
                    data = json.loads(message)
                    message_type = data.get("type")
                    if message_type == "start":
                        sample_rate = int(data.get("sample_rate") or sample_rate)
                    elif message_type == "error":
                        raise RuntimeError(str(data.get("message") or "TTS cache synthesis failed"))
                    elif message_type == "end":
                        if not pcm:
                            raise RuntimeError("TTS cache synthesis returned no audio")
                        return bytes(pcm), sample_rate
                raise RuntimeError("TTS cache websocket closed before end message")

        return await asyncio.wait_for(run(), timeout=self.request_timeout_s)

    async def prime_missing(self, *, tts_url: str, speaker_id: str) -> dict[str, int]:
        if not self.enabled:
            return {"loaded": 0, "generated": 0, "failed": 0}

        loaded = self.load_existing(speaker_id=speaker_id)
        generated = 0
        failed = 0
        if not self.prime_on_startup:
            return {"loaded": loaded, "generated": 0, "failed": 0}

        for cue in self.cues:
            key = (cue.purpose, cue.language)
            if key in self._audio:
                continue
            path = self._cache_path(cue, speaker_id)
            try:
                pcm16, sample_rate = await self._synthesize_cue(
                    cue,
                    tts_url=tts_url,
                    speaker_id=speaker_id,
                )
                self._write_wav_atomic(path, pcm16=pcm16, sample_rate=sample_rate)
                audio = self._read_wav(path, cue)
                if audio is None:
                    raise RuntimeError("generated fast-first WAV could not be read back")
                self._audio[key] = audio
                generated += 1
                logger.info(
                    "Primed fast-first cue purpose=%s language=%s chars=%s audio_ms=%.1f path=%s",
                    cue.purpose,
                    cue.language,
                    len(cue.text),
                    len(pcm16) / (sample_rate * 2) * 1000.0,
                    path,
                )
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Fast-first cue prime failed purpose=%s language=%s: %s",
                    cue.purpose,
                    cue.language,
                    exc,
                )
        return {"loaded": loaded, "generated": generated, "failed": failed}

    @property
    def ready_count(self) -> int:
        return len(self._audio)
