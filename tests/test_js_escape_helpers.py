"""Every JS HTML-escape chain that escapes `"` must also escape `'` (and `&`),
so values interpolated into single-quoted attributes or JSON-in-onclick
cannot break out. No JS test runner exists, so this scans the source."""

import re
from pathlib import Path

JS_DIR = Path(__file__).resolve().parent.parent / "pharmagpt" / "static" / "js"
_QUOT = re.compile(r"""\.replace\(/"/g,\s*['"]&quot;['"]\)""")
_APOS = re.compile(r"&#0?39;|&apos;")


def test_quote_escapes_also_escape_apostrophe_and_ampersand():
    offenders = []
    for path in sorted(JS_DIR.glob("*.js")):
        src = path.read_text(encoding="utf-8")
        for m in _QUOT.finditer(src):
            window = src[max(0, m.start() - 200): m.end() + 120]
            line = src.count("\n", 0, m.start()) + 1
            if not _APOS.search(window) or "&amp;" not in window:
                offenders.append(f"{path.name}:{line}")
    assert not offenders, f"incomplete HTML escaping at: {offenders}"


def test_report_wizard_has_no_inline_string_args():
    src = (JS_DIR / "report.js").read_text(encoding="utf-8")
    assert "function esc(" not in src
    assert "selectLinkedQual(${Number(q.id)}, this.dataset.eq)" in src
