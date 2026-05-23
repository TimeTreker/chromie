from __future__ import annotations


class LedController:
    """Placeholder LED helper for future hardware integration."""

    VALID_COLORS = {"off", "white", "red", "green", "blue", "yellow", "purple"}

    def normalize_color(self, color: str) -> str:
        color = color.strip().lower()
        if color not in self.VALID_COLORS:
            return "white"
        return color
