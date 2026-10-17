from __future__ import annotations

import asyncio
import json
import unittest

from orchestrator.clients.asr_client import ASRClient


class _Socket:
    close_code = None

    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.closed = False

    async def send(self, audio: bytes) -> None:
        del audio

    async def recv(self) -> str:
        if not self.replies:
            await asyncio.sleep(10)
        return json.dumps(self.replies.pop(0))

    async def close(self) -> None:
        self.closed = True


class ASRClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_must_echo_the_utterance_sequence(self) -> None:
        client = ASRClient("ws://asr")
        socket = _Socket(
            [
                {"type": "final", "sequence": 1, "text": "hello"},
                {"type": "final", "sequence": 1, "text": "late"},
            ]
        )
        client.ws = socket
        self.assertEqual((await client.transcribe(b"a"))["text"], "hello")
        with self.assertRaisesRegex(RuntimeError, "sequence 1 does not match utterance 2"):
            await client.transcribe(b"b")
        self.assertTrue(socket.closed)
        self.assertIsNone(client.ws)

    async def test_timeout_resets_the_connection(self) -> None:
        client = ASRClient("ws://asr")
        socket = _Socket([])
        client.ws = socket
        with self.assertRaises(asyncio.TimeoutError):
            await client.transcribe(b"a", timeout=0.01)
        self.assertTrue(socket.closed)
        self.assertIsNone(client.ws)


if __name__ == "__main__":
    unittest.main()
