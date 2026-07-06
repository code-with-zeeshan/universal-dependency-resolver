"""orjson-backed JSON utility — 3-5x faster than stdlib json.

Replaces ``import json`` in hot-path modules.

Drop-in replacement for common patterns:
  - ``json.loads(s)``  → ``_json.loads(s)``
  - ``json.dumps(obj)`` → ``_json.dumps(obj)``
  - ``json.dumps(obj, indent=2)`` → ``_json.dumps(obj, indent=2)``
  - ``json.dumps(obj, sort_keys=True)`` → ``_json.dumps(obj, sort_keys=True)``
  - ``json.dumps(obj, default=str)`` → ``_json.dumps(obj, default=str)``

NOT supported (falls back to stdlib):
  - ``json.dump(obj, file, ...)`` → use ``file.write(_json.dumps(obj, ...))``
  - ``json.load(file)`` → use ``_json.loads(file.read())``
"""

from typing import Any

import orjson


def loads(s: str | bytes) -> Any:
    """Deserialize JSON *s* (string or bytes) to a Python object."""
    return orjson.loads(s)


def dumps(
    obj: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    default: Any = None,
) -> str:
    """Serialize *obj* to a JSON *string* (PEP 393 compatible)."""
    option = 0
    if indent is not None:
        option |= orjson.OPT_INDENT_2
    if sort_keys:
        option |= orjson.OPT_SORT_KEYS

    kwargs: dict[str, Any] = {}
    if default is not None:
        kwargs["default"] = default

    raw: bytes = orjson.dumps(obj, option=option, **kwargs)
    return raw.decode("utf-8")


JSONDecodeError = orjson.JSONDecodeError
