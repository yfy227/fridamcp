"""JavaScript generation helpers."""

import json
from typing import Any


def js_string(value: Any) -> str:
    """Return a safe JavaScript string literal for *value*."""
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def js_json(value: Any) -> str:
    """Return a safe JavaScript literal for JSON-serialisable values."""
    return json.dumps(value, ensure_ascii=False)
