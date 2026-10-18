from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from orchestrator.clients import tts_client


class _FakeSocket:
    def __init__(self, frames: list[object]) -> None:
        self.frames = frames
        self.sent: list[str] = []

    async def __aenter__(self) -> "_FakeSocket":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    def __aiter__(self):
        async def frames():
            for frame in self.frames:
                yield frame

        return frames()


def _synthesize(frames: list[object]) -> tuple[bytes, int]:
    socket = _FakeSocket(frames)
    with mock.patch.object(tts_client.websockets, "connect", return_value=socket, create=True):
        return asyncio.run(
            tts_client.TTSClient("ws://tts").synthesize(
                text="hi", speaker_id="default", request_id="r1"
            )
        )


class TTSClientTests(unittest.TestCase):
    def test_rate_comes_from_the_start_frame(self) -> None:
        audio, rate = _synthesize(
            [
                json.dumps({"type": "start", "sample_rate": 24000}),
                b"\x01\x00",
                json.dumps({"type": "end"}),
            ]
        )
        self.assertEqual((audio, rate), (b"\x01\x00", 24000))

    def test_missing_rate_fails_instead_of_guessing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "did not declare sample_rate"):
            _synthesize([json.dumps({"type": "start"}), json.dumps({"type": "end"})])
        with self.assertRaisesRegex(RuntimeError, "without a start frame"):
            _synthesize([json.dumps({"type": "end"})])


if __name__ == "__main__":
    unittest.main()
