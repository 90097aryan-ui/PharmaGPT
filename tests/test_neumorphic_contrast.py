"""WCAG 2.x AA (4.5:1) for the text colour tokens of the neumorphic skin on the surfaces it uses."""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "pharmagpt" / "static" / "css" / "neumorphic.css"


def _tokens():
    root = re.search(r":root\s*\{(.*?)\n\}", CSS.read_text(encoding="utf-8"), re.S).group(1)
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", root))


def _lum(hex_):
    ch = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_tokens_meet_aa_on_all_surfaces():
    t = _tokens()
    for fg in ("--text", "--text-muted", "--text-disabled"):
        for bg in ("--bg", "--surface", "--bg-secondary"):
            ratio = contrast(t[fg], t[bg])
            assert ratio >= 4.5, f"{fg} on {bg} is {ratio:.2f}:1 (< 4.5:1)"
