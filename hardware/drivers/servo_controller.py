from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ServoController:
    """Placeholder servo helper.

    Fill this with your actual servo SDK/PWM implementation when hardware is
    ready. Keep safety clamps close to the hardware layer.
    """

    def __init__(self, yaw_limit: tuple[float, float] = (-90.0, 90.0), pitch_limit: tuple[float, float] = (-45.0, 45.0)) -> None:
        self.yaw_limit = yaw_limit
        self.pitch_limit = pitch_limit

    def normalize_head_pose(self, yaw_degrees: float, pitch_degrees: float) -> tuple[float, float]:
        yaw = clamp(yaw_degrees, *self.yaw_limit)
        pitch = clamp(pitch_degrees, *self.pitch_limit)
        return yaw, pitch
