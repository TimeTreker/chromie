import asyncio
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable, Optional

import aiohttp
import websockets

logger = logging.getLogger("chromie-orchestrator")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ServiceReadinessGate:
    """
    Startup readiness gate for Chromie.

    The orchestrator should not open the microphone or start the chat loop until:

    - LLM / Ollama is reachable and the configured model can respond.
    - ASR websocket is reachable and returns an ASR health pong.
    - TTS websocket is reachable and returns a TTS health pong.
    - The configured TTS speaker exists, unless speaker validation is disabled.

    wait_until_ready() returns a ready ASR websocket so orchestrator.py can reuse it.
    """

    def __init__(
        self,
        *,
        asr_url: str,
        tts_url: str,
        llm_url: str,
        ollama_model: str,
        speaker_id: str,
        get_http_session: Optional[Callable[[], Awaitable[aiohttp.ClientSession]]] = None,
    ):
        self.asr_url = asr_url
        self.tts_url = tts_url
        self.llm_url = llm_url
        self.ollama_model = ollama_model
        self.speaker_id = speaker_id
        self.get_http_session = get_http_session

        self.ready_check_interval_sec = max(
            0.1,
            float(os.getenv("ORCH_READY_CHECK_INTERVAL_SEC", "3")),
        )
        self.ready_status_interval_sec = max(
            0.0,
            float(os.getenv("ORCH_READY_STATUS_INTERVAL_SEC", "15")),
        )
        self.ready_llm_timeout_sec = max(
            1.0,
            float(os.getenv("ORCH_READY_LLM_TIMEOUT_SEC", "90")),
        )
        self.ready_ws_timeout_sec = max(
            1.0,
            float(os.getenv("ORCH_READY_WS_TIMEOUT_SEC", "10")),
        )
        self.ready_llm_num_ctx = int(os.getenv("ORCH_READY_LLM_NUM_CTX", "128"))
        self.ready_llm_num_predict = int(os.getenv("ORCH_READY_LLM_NUM_PREDICT", "2"))
        self.ready_validate_tts_speaker = env_bool(
            "ORCH_READY_VALIDATE_TTS_SPEAKER",
            True,
        )

        self.ready_message = os.getenv(
            "ORCH_READY_MESSAGE",
            "wait llm, asr and tts ready to talk...",
        )
        self.ready_done_message = os.getenv(
            "ORCH_READY_DONE_MESSAGE",
            "OK, Chromie ready to talk...",
        )

        self.module_state = {
            "llm": "waiting",
            "asr": "waiting",
            "tts": "waiting",
        }
        self.last_error = {
            "llm": "",
            "asr": "",
            "tts": "",
        }
        self._announced_ready = set()
        self._owned_http_session: Optional[aiohttp.ClientSession] = None

    async def close(self):
        if self._owned_http_session is not None and not self._owned_http_session.closed:
            await self._owned_http_session.close()
        self._owned_http_session = None

    async def _http_session(self) -> aiohttp.ClientSession:
        if self.get_http_session is not None:
            return await self.get_http_session()

        if self._owned_http_session is None or self._owned_http_session.closed:
            connector = aiohttp.TCPConnector(
                limit=4,
                limit_per_host=4,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=10,
                sock_connect=10,
                sock_read=None,
            )
            self._owned_http_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )

        return self._owned_http_session

    def _announce_ready_once(self, service_name: str):
        if service_name in self._announced_ready:
            return

        self._announced_ready.add(service_name)
        message = f"{service_name} ready..."
        print(message, flush=True)
        logger.info(message)

    def _set_waiting(self, service_name: str, reason: str):
        self.module_state[service_name] = "waiting"
        self.last_error[service_name] = reason
        logger.info("%s not ready yet: %s", service_name, reason)

    def _set_ready(self, service_name: str):
        self.module_state[service_name] = "ready"
        self.last_error[service_name] = ""
        self._announce_ready_once(service_name)

    def _waiting_services(self) -> list[str]:
        return [
            name
            for name, state in self.module_state.items()
            if state != "ready"
        ]

    async def check_llm_ready(self) -> tuple[bool, str]:
        """
        Check that Ollama is reachable and the configured model can complete
        a tiny non-streaming generation.

        This also warms the model before the first real user interaction.
        """
        payload = {
            "model": self.ollama_model,
            "prompt": "Reply with OK.",
            "stream": False,
            "think": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "options": {
                "num_ctx": self.ready_llm_num_ctx,
                "num_predict": self.ready_llm_num_predict,
                "temperature": 0.0,
            },
        }

        try:
            session = await self._http_session()
            timeout = aiohttp.ClientTimeout(total=self.ready_llm_timeout_sec)

            async with session.post(
                self.llm_url,
                json=payload,
                timeout=timeout,
            ) as resp:
                body = await resp.text()

                if resp.status != 200:
                    return False, f"HTTP {resp.status}: {body[:300]}"

                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    return False, f"invalid JSON from Ollama: {body[:300]}"

                if data.get("error"):
                    return False, str(data.get("error"))

                return True, "ok"

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return False, str(exc)

    async def connect_asr_ready(self) -> tuple[bool, str, Optional[Any]]:
        """
        Connect to ASR, send a health ping, and return the websocket if ready.

        The returned websocket is intentionally kept open so orchestrator.py can
        reuse it for real ASR requests after startup.
        """
        ws = None

        try:
            ws = await websockets.connect(
                self.asr_url,
                max_size=10**7,
                open_timeout=self.ready_ws_timeout_sec,
                ping_interval=20,
                ping_timeout=20,
            )

            await ws.send(json.dumps({"type": "health"}))
            msg = await asyncio.wait_for(
                ws.recv(),
                timeout=self.ready_ws_timeout_sec,
            )

            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                await ws.close()
                return False, f"invalid JSON from ASR health check: {msg!r}", None

            if data.get("type") == "pong" and data.get("service") == "asr":
                return True, "ok", ws

            await ws.close()
            return False, f"unexpected ASR health response: {data}", None

        except asyncio.CancelledError:
            if ws is not None:
                await ws.close()
            raise
        except Exception as exc:
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
            return False, str(exc), None

    async def check_tts_ready(self) -> tuple[bool, str]:
        """
        Check that TTS websocket is reachable, model is loaded, and the selected
        speaker profile is available.
        """
        try:
            async with websockets.connect(
                self.tts_url,
                max_size=10**7,
                open_timeout=self.ready_ws_timeout_sec,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                await ws.send(json.dumps({"type": "health"}))
                msg = await asyncio.wait_for(
                    ws.recv(),
                    timeout=self.ready_ws_timeout_sec,
                )

                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    return False, f"invalid JSON from TTS health check: {msg!r}"

                if data.get("type") != "pong" or data.get("service") != "tts":
                    return False, f"unexpected TTS health response: {data}"

                speakers = data.get("speakers") or []
                if self.ready_validate_tts_speaker and self.speaker_id not in speakers:
                    return (
                        False,
                        f"speaker_id={self.speaker_id!r} not found; "
                        f"available={speakers}",
                    )

                return True, "ok"

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return False, str(exc)

    async def _wait_llm_ready(self):
        while True:
            ok, reason = await self.check_llm_ready()
            if ok:
                self._set_ready("llm")
                return

            self._set_waiting("llm", reason)
            await asyncio.sleep(self.ready_check_interval_sec)

    async def _wait_asr_ready(self) -> Any:
        while True:
            ok, reason, ws = await self.connect_asr_ready()
            if ok and ws is not None:
                self._set_ready("asr")
                return ws

            self._set_waiting("asr", reason)
            await asyncio.sleep(self.ready_check_interval_sec)

    async def _wait_tts_ready(self):
        while True:
            ok, reason = await self.check_tts_ready()
            if ok:
                self._set_ready("tts")
                return

            self._set_waiting("tts", reason)
            await asyncio.sleep(self.ready_check_interval_sec)

    async def _status_printer(self, done_event: asyncio.Event):
        print(self.ready_message, flush=True)
        logger.info(self.ready_message)

        if self.ready_status_interval_sec <= 0:
            await done_event.wait()
            return

        while not done_event.is_set():
            try:
                await asyncio.wait_for(
                    done_event.wait(),
                    timeout=self.ready_status_interval_sec,
                )
            except asyncio.TimeoutError:
                waiting = self._waiting_services()
                if waiting:
                    print(self.ready_message, flush=True)
                    logger.info("Waiting for modules: %s", ", ".join(waiting))

    async def wait_until_ready(self) -> Any:
        """
        Wait until LLM, ASR, and TTS are ready.

        Returns:
            The ready ASR websocket. Assign it to orchestrator.asr_ws.
        """
        done_event = asyncio.Event()

        status_task = asyncio.create_task(self._status_printer(done_event))
        llm_task = asyncio.create_task(self._wait_llm_ready())
        asr_task = asyncio.create_task(self._wait_asr_ready())
        tts_task = asyncio.create_task(self._wait_tts_ready())

        tasks = [llm_task, asr_task, tts_task]

        try:
            _, asr_ws, _ = await asyncio.gather(*tasks)

            done_event.set()
            await status_task

            print(self.ready_done_message, flush=True)
            logger.info(self.ready_done_message)

            return asr_ws

        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            status_task.cancel()
            raise

        except Exception:
            for task in tasks:
                task.cancel()
            status_task.cancel()
            raise

    async def wait_for_asr_only(self) -> Any:
        """
        Runtime ASR reconnect helper.

        This is useful after startup if the ASR websocket drops during a session.
        It does not check LLM/TTS because the full readiness gate is only needed
        before microphone startup.
        """
        while True:
            ok, reason, ws = await self.connect_asr_ready()
            if ok and ws is not None:
                return ws

            logger.warning("ASR not ready yet: %s", reason)
            await asyncio.sleep(self.ready_check_interval_sec)
