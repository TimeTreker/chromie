from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.tts_reference import install_reference, validate_reference_dir


def wav_fixture(path: Path, *, payload: bytes = b"\x00\x00" * 32) -> None:
    data_size = len(payload)
    riff_size = 36 + data_size
    header = (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
    )
    path.write_bytes(header + payload)


class TtsReferenceTests(unittest.TestCase):
    def test_install_and_validate_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "voice.wav"
            output = root / "installed"
            wav_fixture(source)
            result = install_reference(
                source_wav=source,
                transcript=" 你好， 我是 Chromie。 ",
                license_id="owner-authorized",
                output_dir=output,
            )
            self.assertEqual(result["text"], "你好， 我是 Chromie。")
            self.assertEqual(result["license_id"], "owner-authorized")
            self.assertTrue((output / "reference.wav").is_file())
            self.assertEqual(validate_reference_dir(output)["audio_sha256"], result["audio_sha256"])

    def test_validation_rejects_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_fixture(root / "reference.wav")
            (root / "reference.json").write_text(
                json.dumps(
                    {
                        "text": "你好",
                        "license_id": "owner-authorized",
                        "audio_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_reference_dir(root)

    def test_install_requires_transcript_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "voice.wav"
            wav_fixture(source)
            with self.assertRaisesRegex(ValueError, "transcript"):
                install_reference(
                    source_wav=source,
                    transcript="",
                    license_id="owner-authorized",
                    output_dir=root / "out-a",
                )
            with self.assertRaisesRegex(ValueError, "license"):
                install_reference(
                    source_wav=source,
                    transcript="你好",
                    license_id="",
                    output_dir=root / "out-b",
                )
