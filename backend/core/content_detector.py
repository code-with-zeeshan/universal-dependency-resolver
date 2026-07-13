"""Content-based manifest detection via file signature sniffing.

Falls back to ``python-magic`` when available; uses hardcoded byte signatures
when it is not.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Byte signatures for common manifest formats.
# Format: (offset, bytes, mime_type, label)
FILE_SIGNATURES: list[tuple[int, bytes, str, str]] = [
    (0, b"{", "application/json", "json"),
    (0, b"<", "application/xml", "xml"),
    (0, b"[package]", "text/x-pkg-config", "cabal"),
    (0, b'name = "', "text/x-toml", "cargo_toml"),
    (0, b"[package]\n", "text/x-toml", "cargo_toml"),
    (0, b"[dependencies]\n", "text/x-toml", "cargo_toml"),
    (0, b"#", "text/plain", "script"),
    (0, b"from ", "text/x-python", "python"),
    (0, b"import ", "text/x-python", "python"),
]

# Maps expected content type label → list of manifest parser keys that
# might apply.  The first match wins.
CONTENT_TO_PARSERS: dict[str, list[str]] = {
    "json": [
        "package_lock",
        "composer_lock",
        "gemfile_lock",
        "pipfile_lock",
        "poetry_lock",
        "uv_lock",
        "mix_lock",
        "package_resolved",
        "podfile_lock",
    ],
    "xml": ["maven", "nuget"],
    "cargo_toml": ["cargo_toml"],
    "cabal": ["cabal"],
}


def sniff_content(path: str) -> str | None:
    """Read the first 4 KB of *path* and return a content-type label.

    Returns ``None`` if the file cannot be read or no signature matches.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(4096)
    except OSError:
        return None

    # Try python-magic first (optional dependency)
    try:
        import magic

        try:
            mime = magic.from_file(path, mime=True)
            if mime and mime != "application/octet-stream":
                return mime
        except Exception:
            pass
    except ImportError:
        pass

    # Fallback: check byte signatures
    stripped = header.lstrip()
    for offset, sig, _mime, _label in FILE_SIGNATURES:
        if len(stripped) > offset and stripped[offset : offset + len(sig)] == sig:
            return _label

    return None


def suggest_parsers(content_type: str) -> list[str]:
    """Return parser keys that are compatible with the detected content type."""
    return CONTENT_TO_PARSERS.get(content_type, [])
