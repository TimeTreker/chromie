"""Adapters from maintained legacy scenario formats to the common contract."""

from .legacy_json import LegacyJsonAdapter, normalize_json_file, normalize_payload

__all__ = ["LegacyJsonAdapter", "normalize_json_file", "normalize_payload"]
