"""Tiny Markdown -> HTML for notebook display (serverless notebooks don't ship the `markdown` package).

Handles only what CareFinder emits: #/##/###/#### headings, **bold**, _italic_, > quotes, - bullets
(two levels), blank-line paragraphs.
"""

from __future__ import annotations

import html
import re

_STYLE = ("<style>.cf{font-family:system-ui,sans-serif;line-height:1.45;max-width:980px}"
          ".cf h3{margin:.6em 0 .2em}.cf h4{margin:1em 0 .2em;padding-top:.6em;border-top:1px solid #8884}"
          ".cf blockquote{margin:.3em 0;padding:.3em .8em;border-left:3px solid #e8a33d;background:#e8a33d14}"
          ".cf ul{margin:.2em 0 .2em 1.2em;padding:0}.cf li{margin:.1em 0}</style>")


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<i>\1</i>", text)
    return text


def md_to_html(md: str) -> str:
    out: list[str] = [_STYLE, '<div class="cf">']
    depth = 0  # open <ul> levels

    def close_lists(to=0):
        nonlocal depth
        while depth > to:
            out.append("</ul>")
            depth -= 1

    for raw in md.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(\s*)- (.*)$", line)
        if m:
            level = 2 if len(m.group(1)) >= 2 else 1
            while depth < level:
                out.append("<ul>")
                depth += 1
            close_lists(level)
            out.append(f"<li>{_inline(m.group(2))}</li>")
            continue
        close_lists()
        if not line.strip():
            continue
        h = re.match(r"^(#{1,4}) (.*)$", line)
        if h:
            n = len(h.group(1))
            out.append(f"<h{n}>{_inline(h.group(2))}</h{n}>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    close_lists()
    out.append("</div>")
    return "\n".join(out)
