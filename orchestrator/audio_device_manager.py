import os
import re
import sounddevice as sd


BAD_NAMES = (
    "default",
    "sysdefault",
    "pipewire",
    "pulse",
    "dmix",
    "front",
    "surround",
)


def parse_index(value):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


class AudioDeviceManager:
    def __init__(self):
        self.devices = sd.query_devices()

    def close(self):
        pass

    def _score_device(self, index, dev, kind):
        name = str(dev.get("name", ""))
        lname = name.lower()
        score = 0

        if kind == "input":
            if dev.get("max_input_channels", 0) <= 0:
                return -9999
            if "monitor" in lname:
                return -9999
            if "alsa_input" in lname:
                score += 100
            if "usb" in lname:
                score += 80
            if "source" in lname:
                score += 20
            score += min(int(dev.get("max_input_channels", 0)), 2) * 5
        else:
            if dev.get("max_output_channels", 0) <= 0:
                return -9999
            if "monitor" in lname:
                return -9999
            if "alsa_output" in lname:
                score += 100
            if "usb" in lname:
                score += 80
            if "sink" in lname:
                score += 20
            score += min(int(dev.get("max_output_channels", 0)), 2) * 5

        if any(lname == bad or lname.startswith(bad) for bad in BAD_NAMES):
            score -= 60

        if index in sd.default.device:
            score += 5

        return score

    def _find_by_name(self, pattern, kind):
        pattern = (pattern or "").strip()
        if not pattern:
            return None
        regex = re.compile(re.escape(pattern), re.I)
        for idx, dev in enumerate(self.devices):
            if regex.search(str(dev.get("name", ""))):
                if kind == "input" and dev.get("max_input_channels", 0) > 0 and "monitor" not in str(dev.get("name", "")).lower():
                    return idx
                if kind == "output" and dev.get("max_output_channels", 0) > 0:
                    return idx
        return None

    def _choose(self, kind):
        env_index = parse_index(os.getenv("INPUT_DEVICE_INDEX" if kind == "input" else "OUTPUT_DEVICE_INDEX"))
        if env_index is not None:
            return env_index

        env_name = os.getenv("INPUT_DEVICE_NAME" if kind == "input" else "OUTPUT_DEVICE_NAME", "")
        idx = self._find_by_name(env_name, kind)
        if idx is not None:
            return idx

        default_idx = sd.default.device[0 if kind == "input" else 1]
        candidates = []
        for idx, dev in enumerate(self.devices):
            score = self._score_device(idx, dev, kind)
            if score > -9999:
                candidates.append((score, idx))

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        return default_idx

    def get_input_params(self):
        idx = self._choose("input")
        dev = sd.query_devices(idx)
        rate = int(float(dev.get("default_samplerate") or 48000))
        channels = min(1, int(dev.get("max_input_channels") or 1)) or 1
        block_ms = int(os.getenv("INPUT_BLOCK_MS", "30"))
        blocksize = max(1, int(rate * block_ms / 1000))
        return {
            "device": idx,
            "name": dev.get("name"),
            "rate": rate,
            "channels": channels,
            "block_ms": block_ms,
            "blocksize": blocksize,
            "latency": os.getenv("INPUT_LATENCY", "low"),
        }

    def get_output_params(self):
        idx = self._choose("output")
        dev = sd.query_devices(idx)
        rate = int(float(dev.get("default_samplerate") or 48000))
        channels = min(2, int(dev.get("max_output_channels") or 2)) or 2
        block_ms = int(os.getenv("OUTPUT_BLOCK_MS", "40"))
        blocksize = max(1, int(rate * block_ms / 1000))
        return {
            "device": idx,
            "name": dev.get("name"),
            "rate": rate,
            "channels": channels,
            "block_ms": block_ms,
            "blocksize": blocksize,
            "latency": os.getenv("OUTPUT_LATENCY", "low"),
        }
