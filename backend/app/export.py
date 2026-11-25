"""
Standalone HTML export: one self-contained .html file that works offline (double-click to open,
e-mail it, archive it). It inlines the page's CSS, the chart library, every JS module the page
imports (bundled into plain scripts) and the report data itself.
"""
from __future__ import annotations

import re
from html import escape

from . import config
from .engine.research import dumps

_IMPORT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*["'](\./[\w.-]+\.js)["'];?""", re.S)
_EXPORT = re.compile(r"^export\s+(?:async\s+)?(function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.M)


def _js(name: str) -> str:
    p = (config.FRONTEND_DIR / "js" / name).resolve()
    if p.parent != (config.FRONTEND_DIR / "js").resolve() or not p.exists():
        raise FileNotFoundError(name)
    return p.read_text(encoding="utf-8")


def bundle(entry: str) -> str:
    """Turn an ES-module graph (frontend/js/<entry> + its ./imports) into one classic script."""
    order, seen = [], set()

    def visit(name, stack=()):
        if name in seen:
            return
        if name in stack:
            raise ValueError(f"Import cycle: {' -> '.join(stack + (name,))}")
        src = _js(name)
        for _, dep in _IMPORT.findall(src):
            visit(dep[2:], stack + (name,))
        seen.add(name)
        order.append((name, src))

    visit(entry)
    parts = ["(function(){'use strict';const __m={};"]
    for name, src in order:
        def imp(m):
            names = []
            for raw in m.group(1).split(","):
                raw = raw.strip()
                if not raw:
                    continue
                a, _, b = raw.partition(" as ")
                names.append(f"{a.strip()}: {b.strip()}" if b else a.strip())
            return f'const {{ {", ".join(names)} }} = __m["{m.group(2)[2:]}"];'
        body = _IMPORT.sub(imp, src)
        exports = [m.group(2) for m in _EXPORT.finditer(body)]
        body = _EXPORT.sub(lambda m: m.group(0)[len("export "):].lstrip(), body)
        parts.append(f'__m["{name}"]=(function(){{\n{body}\n;return {{{", ".join(exports)}}};}})();')
    parts.append("})();")
    return "\n".join(parts)


def _script_safe(s: str) -> str:
    return s.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def standalone(page: str, entry_js: str, payload: dict, title: str) -> str:
    html = (config.FRONTEND_DIR / page).read_text(encoding="utf-8")

    def css(m):
        p = config.FRONTEND_DIR / m.group(1)
        return f"<style>\n{p.read_text(encoding='utf-8')}\n</style>"
    html = re.sub(r'<link rel="stylesheet" href="([\w/.-]+\.css)">', css, html)
    vendor = (config.FRONTEND_DIR / "vendor" / "lightweight-charts.standalone.js").read_text(encoding="utf-8")
    html = html.replace('<script src="vendor/lightweight-charts.standalone.js"></script>',
                        f"<script>{_script_safe(vendor)}</script>")
    data = dumps(payload).replace("</", "<\\/")
    html = re.sub(r'<script type="module" src="js/[\w.-]+\.js"></script>',
                  lambda _: f"<script>window.__STANDALONE__=true;window.__REPORT__={data};</script>\n"
                            f"<script>{_script_safe(bundle(entry_js))}</script>", html)
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{escape(title)}</title>", html, count=1)
    return html
