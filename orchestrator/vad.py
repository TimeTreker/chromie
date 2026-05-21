import collections
import webrtcvad


class VAD:
    def __init__(self, mode=3, sample_rate=16000, frame_duration_ms=30, silence_timeout_ms=650):
        self.vad = webrtcvad.Vad(int(mode))
        self.sample_rate = int(sample_rate)
        self.frame_duration_ms = int(frame_duration_ms)
        self.frame_bytes = int(self.sample_rate * self.frame_duration_ms / 1000) * 2
        self.silence_frames_needed = max(1, int(silence_timeout_ms / frame_duration_ms))
        self.triggered = False
        self.silence_frames = 0
        self.frames = []
        self.pre_roll = collections.deque(maxlen=8)

    def reset(self):
        self.triggered = False
        self.silence_frames = 0
        self.frames = []
        self.pre_roll.clear()

    def process_chunk(self, frame: bytes):
        if len(frame) != self.frame_bytes:
            return False, False, b""

        is_speech = self.vad.is_speech(frame, self.sample_rate)
        started = False
        ended = False
        audio = b""

        if not self.triggered:
            self.pre_roll.append(frame)
            if is_speech:
                self.triggered = True
                started = True
                self.silence_frames = 0
                self.frames = list(self.pre_roll)
        else:
            self.frames.append(frame)
            if is_speech:
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                if self.silence_frames >= self.silence_frames_needed:
                    ended = True
                    audio = b"".join(self.frames)
                    self.reset()

        return started, ended, audio
