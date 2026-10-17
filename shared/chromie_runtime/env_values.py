"""Strict parsing of operator-supplied setting values.

Every Chromie Python surface that can import ``shared`` parses boolean flags
through :func:`parse_bool` and numbers through :func:`parse_int` and
:func:`parse_float`. All three share one rule: an unset (``None``) or
empty/whitespace-only value means "use the default"; any other value must parse
and lie inside its declared range, or the parser raises with the setting name.
Nothing is silently clamped or replaced by the default.
"""
from __future__ import annotations

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class InvalidBooleanSetting(ValueError):
    """An environment flag carried a value outside the accepted vocabulary."""


class InvalidNumericSetting(ValueError):
    """A numeric setting did not parse or fell outside its declared range."""


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


def _check_range(
    value: int | float,
    *,
    name: str,
    minimum: int | float | None,
    maximum: int | float | None,
) -> None:
    if minimum is not None and value < minimum:
        raise InvalidNumericSetting(f"{name} must be >= {minimum}; got {value}")
    if maximum is not None and value > maximum:
        raise InvalidNumericSetting(f"{name} must be <= {maximum}; got {value}")


def parse_int(
    raw: object,
    *,
    name: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse one integer setting under the shared empty-means-default rule."""

    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except ValueError as exc:
            raise InvalidNumericSetting(
                f"{name} must be an integer; got {raw!r}"
            ) from exc
    _check_range(value, name=name, minimum=minimum, maximum=maximum)
    return value


def parse_float(
    raw: object,
    *,
    name: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse one number setting under the shared empty-means-default rule."""

    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as exc:
            raise InvalidNumericSetting(
                f"{name} must be a number; got {raw!r}"
            ) from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidNumericSetting(f"{name} must be finite; got {raw!r}")
    _check_range(value, name=name, minimum=minimum, maximum=maximum)
    return value


__all__ = [
    "FALSE_VALUES",
    "TRUE_VALUES",
    "InvalidBooleanSetting",
    "InvalidNumericSetting",
    "parse_bool",
    "parse_float",
    "parse_int",
]
