#!/usr/bin/env python3
"""Generate a simple SVG badge with label, value, and color.

No external dependencies — uses pure string templates.
"""

import argparse
import sys

_SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="m">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </mask>
  <g mask="url(#m)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>"""


def _text_width(text: str) -> int:
    """Approximate pixel width of text in the badge font."""
    # Rough char-width approximation: most chars ~7px, 'i','l','t' ~5px, 'W','M' ~10px
    width = 0
    for ch in text:
        if ch in "iIl t":
            width += 5
        elif ch in "mwWM":
            width += 10
        else:
            width += 7
    return max(width, 10)


def generate_badge(label: str, value: str, color: str = "green") -> str:
    """Generate an SVG badge with *label*, *value*, and *color*.

    *color* is an SVG fill color (e.g. ``"green"``, ``"#dfb317"``, ``"red"``).
    Returns the SVG XML as a string.
    """
    pad = 8
    label_w = _text_width(label) + pad
    value_w = _text_width(value) + pad
    total_w = label_w + value_w

    return _SVG_TEMPLATE.format(
        total_width=total_w,
        label_width=label_w,
        value_width=value_w,
        label_x=pad // 2,
        value_x=label_w + pad // 2,
        label=label,
        value=value,
        color=color,
    )


def _health_color(value: str) -> str:
    """Map a health status string to a badge color."""
    lower = value.strip().lower()
    if lower in ("passing", "ok", "healthy", "true", "yes"):
        return "green"
    if lower in ("failing", "error", "fail", "false", "no"):
        return "red"
    if lower in ("unknown", "?", ""):
        return "lightgrey"
    return "orange"


def main() -> None:
    """Parse CLI args and print or save a badge SVG."""
    parser = argparse.ArgumentParser(description="Generate a simple SVG badge")
    parser.add_argument("--label", default="health", help="Badge label (left side)")
    parser.add_argument("--value", default="unknown", help="Badge value (right side)")
    parser.add_argument(
        "--color",
        default=None,
        help="Badge color (right side). Auto-detected for common status strings.",
    )
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout)")
    args = parser.parse_args()

    color = args.color or _health_color(args.value)

    svg = generate_badge(args.label, args.value, color)

    if args.output:
        with open(args.output, "w") as f:
            f.write(svg)
    else:
        sys.stdout.write(svg)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
