from __future__ import annotations

import asyncio
import unittest

from orchestrator.runtime.runtime_ready_greeting import (
    RuntimeReadyGreetingCoordinator,
    RuntimeReadyGreetingPolicy,
)


class RuntimeReadyGreetingCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_policy_does_not_generate_or_schedule(self) -> None:
        calls: list[str] = []

        async def generate() -> tuple[str, str]:
            calls.append("generate")
            return "嗨！", "test"

        async def schedule(_text: str):
            calls.append("schedule")
            return {"scheduled": True, "generation": 0, "order": 0}

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=False,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
            ),
            generate_greeting=generate,
            is_valid_text=lambda _text: True,
            schedule_text=schedule,
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
        )

        await coordinator.announce()

        self.assertEqual(calls, [])

    async def test_non_device_runtime_skips_before_generation(self) -> None:
        generated = False

        async def generate() -> tuple[str, str]:
            nonlocal generated
            generated = True
            return "嗨！", "test"

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="stdin",
                audio_output_mode="discard",
                timeout_ms=1000,
            ),
            generate_greeting=generate,
            is_valid_text=lambda _text: True,
            schedule_text=lambda _text: asyncio.sleep(0, result={}),
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
        )

        await coordinator.announce()

        self.assertFalse(generated)

    async def test_success_waits_for_playback_start_and_completion(self) -> None:
        scheduled_text: list[str] = []
        key = (4, 8, None)
        waiter = asyncio.get_running_loop().create_future()
        waiter.set_result(True)

        async def schedule(text: str):
            scheduled_text.append(text)
            return {
                "scheduled": True,
                "generation": 4,
                "order": 8,
                "last_order": 9,
            }

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
                speech_enabled=True,
            ),
            generate_greeting=lambda: asyncio.sleep(
                0,
                result=("嗨，我醒啦！", "test"),
            ),
            is_valid_text=lambda text: bool(text),
            schedule_text=schedule,
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={key: waiter},
            next_playback_order=lambda: 10,
        )

        await coordinator.announce()

        self.assertEqual(scheduled_text, ["嗨，我醒啦！"])

    async def test_invalid_generated_text_is_not_scheduled(self) -> None:
        scheduled = False

        async def schedule(_text: str):
            nonlocal scheduled
            scheduled = True
            return {"scheduled": True, "generation": 1, "order": 1}

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
                speech_enabled=True,
            ),
            generate_greeting=lambda: asyncio.sleep(0, result=("", "unavailable")),
            is_valid_text=lambda text: bool(text),
            schedule_text=schedule,
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
        )

        await coordinator.announce()

        self.assertFalse(scheduled)

    async def test_missing_start_waiter_fails_open(self) -> None:
        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
                speech_enabled=True,
            ),
            generate_greeting=lambda: asyncio.sleep(0, result=("嗨！", "test")),
            is_valid_text=lambda text: bool(text),
            schedule_text=lambda _text: asyncio.sleep(
                0,
                result={"scheduled": True, "generation": 2, "order": 3},
            ),
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
        )

        await coordinator.announce()


    async def test_silent_orientation_runs_without_generating_speech(self) -> None:
        calls: list[str] = []

        async def orient():
            calls.append("orient")
            return {
                "status": "completed",
                "capability_id": "soridormi.express_attention",
            }

        async def generate() -> tuple[str, str]:
            calls.append("generate")
            return "不该说话。", "test"

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
                orientation_enabled=True,
                orientation_timeout_ms=1000,
                speech_enabled=False,
            ),
            generate_greeting=generate,
            is_valid_text=lambda _text: True,
            schedule_text=lambda _text: asyncio.sleep(0, result={}),
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
            execute_orientation=orient,
        )

        await coordinator.announce()

        self.assertEqual(calls, ["orient"])

    async def test_orientation_failure_does_not_force_startup_speech(self) -> None:
        generated = False

        async def orient():
            raise RuntimeError("provider unavailable")

        async def generate() -> tuple[str, str]:
            nonlocal generated
            generated = True
            return "不该说话。", "test"

        coordinator = RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=True,
                audio_input_mode="device",
                audio_output_mode="device",
                timeout_ms=1000,
                orientation_enabled=True,
                orientation_timeout_ms=1000,
                speech_enabled=False,
            ),
            generate_greeting=generate,
            is_valid_text=lambda _text: True,
            schedule_text=lambda _text: asyncio.sleep(0, result={}),
            playback_start_key=lambda generation, order, session_id: (
                generation,
                order,
                session_id,
            ),
            playback_start_waiters={},
            next_playback_order=lambda: 0,
            execute_orientation=orient,
        )

        await coordinator.announce()

        self.assertFalse(generated)


if __name__ == "__main__":
    unittest.main()
