from __future__ import annotations

import asyncio
import time
import unittest

from tts.cancellable_worker import RestartableProcessWorker


def _fake_generation_worker(connection) -> None:
    connection.send({"type": "ready"})
    try:
        while True:
            command = connection.recv()
            if command.get("type") == "shutdown":
                connection.send({"type": "stopped"})
                return
            if command.get("type") == "block":
                time.sleep(float(command.get("seconds", 30.0)))
                connection.send({"type": "done"})
                continue
            connection.send({"type": "pong"})
    except (EOFError, BrokenPipeError, OSError):
        return


class RestartableProcessWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_terminates_stale_work_and_restarts_worker(self) -> None:
        worker = RestartableProcessWorker(
            _fake_generation_worker,
            name="chromie-test-generation",
            startup_timeout_s=2.0,
            context_name="forkserver",
        )
        await worker.start()
        try:
            request = asyncio.create_task(
                worker.request({"type": "block", "seconds": 30.0})
            )
            await asyncio.sleep(0.05)
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(request, timeout=2.0)

            self.assertTrue(worker.is_alive)
            self.assertEqual(worker.restart_count, 1)
            response = await asyncio.wait_for(
                worker.request({"type": "ping"}),
                timeout=1.0,
            )
            self.assertEqual(response, {"type": "pong"})
        finally:
            await worker.stop()


if __name__ == "__main__":
    unittest.main()
