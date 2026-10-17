"""Strict parsing of operator-supplied environment values.

Every Chromie Python surface that can import ``shared`` parses boolean flags
through :func:`parse_bool` so a misspelled or unexpected value fails closed with
a clear error instead of silently enabling or disabling a feature.
"""
from __future__ import annotations

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class InvalidBooleanSetting(ValueError):
    """An environment flag carried a value outside the accepted vocabulary."""


def parse_bool(raw: object, *, name: str, default: bool) -> bool:
    """Parse one boolean setting.

    ``None`` (unset) and empty/whitespace-only values return ``default``.
    ``1/true/yes/on`` and ``0/false/no/off`` are accepted case-insensitively.
    Anything else raises :class:`InvalidBooleanSetting`.
    """

    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    normalized = str(raw).strip().casefold()
    if not normalized:
        return default
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise InvalidBooleanSetting(
        f"{name} must be a boolean (1/true/yes/on or 0/false/no/off); got {raw!r}"
    )


__all__ = [
    "FALSE_VALUES",
    "TRUE_VALUES",
    "InvalidBooleanSetting",
    "parse_bool",
]
