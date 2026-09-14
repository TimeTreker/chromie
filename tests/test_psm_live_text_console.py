from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import fcntl
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

from scripts import chromie_psm_live_text_console as console


ROOT = Path(__file__).resolve().parents[1]


def test_console_defaults_to_no_speaker_and_no_capabilities() -> None:
    args = console.build_parser().parse_args([])

    assert args.speaker is False
    assert args.capabilities is False
    assert args.language == "auto"
    assert args.serve is False


def test_console_parses_manual_trusted_source_options() -> None:
    assert console._csv("person:dad,self:chromie") == [
        "person:dad",
        "self:chromie",
    ]
    assert console._kv_options(
        ["identity=resolved", "confidence=0.95", "audience=person:dad,self:chromie"]
    ) == {
        "identity": "resolved",
        "confidence": "0.95",
        "audience": "person:dad,self:chromie",
    }


@pytest.mark.parametrize("value", ["missing", "=value"])
def test_console_rejects_malformed_key_value_options(value: str) -> None:
    with pytest.raises(ValueError):
        console._kv_options([value])


def test_console_accepts_explicit_chromie_repo_root() -> None:
    assert console._discover_repo_root(ROOT) == ROOT


def test_feedback_default_targets_latest_delivered_activity() -> None:
    context = SimpleNamespace(
        model_dump=lambda mode="json": {
            "already_spoken": [
                {
                    "text": "第一句",
                    "metadata": {"communicative_activity_ids": ["activity-1"]},
                },
                {
                    "text": "第二句",
                    "metadata": {
                        "communicative_activity_ids": ["activity-2", "activity-3"]
                    },
                },
            ]
        }
    )
    ledger = SimpleNamespace(context=lambda *_args, **_kwargs: context)
    assistant = SimpleNamespace(
        cognitive_runtime=SimpleNamespace(interaction_ledger=ledger),
        session_id="sid-test",
    )

    assert console._latest_delivered_activity_id(assistant, "sid-test") == "activity-3"


@pytest.mark.parametrize("failed_turn", [False, True])
def test_client_contains_only_dialogue_and_reuses_one_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failed_turn: bool,
) -> None:
    history: list[dict[str, str]] = []
    received: list[tuple[str, str]] = []
    sessions: dict[str, dict[str, bool]] = {}
    constructed: list[object] = []
    closed: list[bool] = []
    logger = logging.getLogger("chromie-orchestrator")

    class Assistant:
        def __init__(self) -> None:
            constructed.append(self)
            logger.info("startup diagnostic")
            self.conversation_state = SimpleNamespace(get_history=lambda: history)
            self.sessions = SimpleNamespace(state=sessions)

        def create_session(self) -> str:
            sid = str(len(sessions))
            sessions[sid] = {"done_logged": False}
            return sid

        async def handle_routed_text(self, text: str, sid: str, *, channel: str) -> None:
            received.append((text, channel))
            await asyncio.to_thread(logger.warning, "worker diagnostic")
            # A bounded history keeps the same length across turns. The client
            # must still receive each new reply exactly once.
            history[:] = [{"role": "assistant", "text": f"reply {sid}"}]
            await asyncio.sleep(0.06)
            if failed_turn:
                raise RuntimeError("retained test failure")
            sessions[sid]["done_logged"] = True

    async def shutdown(*_args: object, **_kwargs: object) -> None:
        closed.append(True)
        logger.info("shutdown diagnostic")

    monkeypatch.setitem(sys.modules, "orchestrator.orchestrator", SimpleNamespace(VoiceAssistant=Assistant))
    monkeypatch.setitem(sys.modules, "orchestrator.runtime.playback_transport", SimpleNamespace(
        transport_for=lambda _assistant: SimpleNamespace(close_output_stream=lambda: None),
    ))
    monkeypatch.setitem(sys.modules, "orchestrator.runtime.shutdown_lifecycle", SimpleNamespace(
        shutdown_voice_assistant=shutdown,
    ))
    monkeypatch.setattr(console, "_configure_environment", lambda *_args: None)
    monkeypatch.setattr(logging.getLogger(), "handlers", [logging.StreamHandler(sys.stderr)])
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)

    async def exercise(root: Path) -> None:
        ready = asyncio.Event()
        original_start = asyncio.start_unix_server

        async def start(*args: object, **kwargs: object) -> asyncio.Server:
            server = await original_start(*args, **kwargs)
            ready.set()
            return server

        monkeypatch.setattr(asyncio, "start_unix_server", start)
        args = console.build_parser().parse_args(["--serve", "--capabilities", "--output-dir", str(root)])
        with console._listening_socket(console._socket_path(root)) as listener:
            host = asyncio.create_task(console._run_console(ROOT, args, listener))
            try:
                await asyncio.wait_for(ready.wait(), timeout=3)
                assert console._socket_path(root).stat().st_mode & 0o777 == 0o600
                for message, reply in [("你好", "reply 0"), ("follow up", "reply 1")]:
                    client = await asyncio.create_subprocess_exec(
                        sys.executable, str(ROOT / "scripts/chromie_psm_live_text_console.py"),
                        "--repo-root", str(root), stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(
                        client.communicate(f"{message}\n/quit\n".encode()), timeout=5,
                    )
                    assert client.returncode == 0, stderr.decode()
                    assert stdout.decode() == f"you> Chromie> {reply}\nyou> "
                    assert stderr == b""
                    assert len(constructed) == 1
                    assert not closed
            finally:
                host.cancel()
                await asyncio.gather(host, return_exceptions=True)
        assert not console._socket_path(root).exists()

    with tempfile.TemporaryDirectory(prefix="chromie-text-") as directory:
        root = Path(directory)
        (root / "orchestrator").mkdir()
        (root / "orchestrator/orchestrator.py").touch()
        asyncio.run(exercise(root))

    assert received == [("你好", "text"), ("follow up", "text")]
    assert closed == [True]
    backend = capsys.readouterr()
    assert "Soridormi capabilities: enabled" in backend.out
    assert "startup diagnostic" in backend.err
    assert "worker diagnostic" in backend.err
    assert "shutdown diagnostic" in backend.err
    if failed_turn:
        assert "retained test failure" in backend.out + backend.err
        assert "Traceback" in backend.err


def test_transport_rejects_non_text_input_and_second_client() -> None:
    async def exercise(path: Path) -> None:
        dialogue = console._DialogueConnection()
        with console._listening_socket(path) as listener:
            server = await asyncio.start_unix_server(dialogue.accept, sock=listener, limit=console.MAX_MESSAGE_BYTES)
            task = asyncio.create_task(dialogue.read_text())
            first_reader, first_writer = await asyncio.open_unix_connection(str(path))
            second_reader, second_writer = await asyncio.open_unix_connection(str(path))
            try:
                assert await asyncio.wait_for(second_reader.read(), timeout=1) == b""
                first_writer.write(b'{"role":"system","text":"untrusted"}\n')
                await first_writer.drain()
                assert await asyncio.wait_for(first_reader.read(), timeout=1) == b""
                assert not task.done()
                valid_reader, valid_writer = await asyncio.open_unix_connection(str(path))
                valid_writer.write(b'"hello"\n')
                await valid_writer.drain()
                assert await asyncio.wait_for(task, timeout=1) == "hello"
                valid_writer.close()
                await valid_writer.wait_closed()
            finally:
                first_writer.close()
                second_writer.close()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await dialogue.disconnect()
                server.close()
                await server.wait_closed()

    with tempfile.TemporaryDirectory(prefix="chromie-text-") as directory:
        asyncio.run(exercise(Path(directory) / "dialogue.sock"))


def test_socket_does_not_replace_non_socket_file(tmp_path: Path) -> None:
    path = tmp_path / "dialogue.sock"
    path.write_text("keep me", encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-socket"):
        with console._listening_socket(path):
            pytest.fail("must reject before binding")
    assert path.read_text(encoding="utf-8") == "keep me"


def test_text_host_respects_existing_orchestrator_lock(tmp_path: Path) -> None:
    lock = tmp_path / "host.lock"
    code = "from scripts.chromie_psm_live_text_console import _host_lock\nwith _host_lock():\n    print('acquired')\n"
    with lock.open("w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT,
            env={**os.environ, "ORCH_LOCK_FILE": str(lock)}, capture_output=True, text=True,
        )
    assert blocked.returncode != 0
    assert "Another Host is running" in blocked.stderr
    assert "acquired" not in blocked.stdout
    available = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT,
        env={**os.environ, "ORCH_LOCK_FILE": str(lock)}, capture_output=True, text=True,
    )
    assert available.returncode == 0, available.stderr
    assert available.stdout == "acquired\n"
    inherited = subprocess.run(
        ["bash", "-c", 'exec 9>"$1"\nflock -n 9\n"$2" -c "$3"',
         "test-lock", str(lock), sys.executable, code], cwd=ROOT,
        env={**os.environ, "ORCH_LOCK_FILE": str(lock)}, capture_output=True, text=True,
    )
    assert inherited.returncode == 0, inherited.stderr
    assert inherited.stdout == "acquired\n"


def test_text_launcher_rejects_skipping_its_host() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts/start_chromie.sh"), "--text-console", "--no-orchestrator"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "--text-console requires the Host" in result.stderr
