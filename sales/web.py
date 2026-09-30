"""The fictional web the agent researches: one small site per lead's company, served from web/<domain>/<page>.html.

Nothing here touches the real internet. Every domain ends in .example, and a domain with no folder
behaves like a site that doesn't exist.
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

WEB = Path(__file__).resolve().parent.parent / "web"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "head"}
# font-size: 0, 0px or 0.0em hides text; 0.8em doesn't.
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:\.0*)?(?![\d.])", re.I)


def domain_of(url_or_email: str) -> str:
    """'https://www.Foo.example/about' -> 'foo.example'; 'ann@foo.example' -> 'foo.example'."""
    s = url_or_email.strip().lower()
    if "@" in s and "/" not in s:
        s = s.rsplit("@", 1)[1]
    host = urlparse(s if "//" in s else "//" + s).hostname or ""
    return host.removeprefix("www.")


def page_name(url: str) -> str:
    s = url.strip()
    path = urlparse(s if "//" in s else "//" + s).path.strip("/").removesuffix(".html")
    return path or "index"


class _Text(HTMLParser):
    """Collects page text and links. With visible_only, elements hidden in their own tag are dropped: the
    hidden attribute, aria-hidden="true", or an inline style of display:none, visibility:hidden or
    font-size:0. Text hidden by a stylesheet class is not detected."""

    def __init__(self, visible_only: bool):
        super().__init__(convert_charrefs=True)
        self.visible_only = visible_only
        self.stack: list[bool] = []  # per open element: is it hidden or skipped?
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def _hidden(self, tag, attrs) -> bool:
        if tag in SKIP:
            return True
        if not self.visible_only:
            return False
        a = dict(attrs)
        return ("hidden" in a or a.get("aria-hidden") == "true"
                or bool(_HIDDEN_STYLE.search(a.get("style") or "")))

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "a" and dict(attrs).get("href"):
            self.links.append(dict(attrs)["href"])
        if tag in {"p", "li", "h1", "h2", "h3", "div", "br", "tr", "a", "header", "footer", "section", "main"}:
            self.parts.append("\n")
        if tag not in VOID:
            self.stack.append(self._hidden(tag, attrs) or (bool(self.stack) and self.stack[-1]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag not in VOID and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not (self.stack and self.stack[-1]):
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(ln.split()) for ln in "".join(self.parts).splitlines())
        return "\n".join(ln for ln in lines if ln)


def fetch(url: str, visible_only: bool) -> dict:
    """Returns {url, title, text, links} for a page, or {url, error} like a failed HTTP request would."""
    domain, name = domain_of(url), page_name(url)
    site = WEB / domain
    if not domain or not site.is_dir():
        return {"url": url, "error": f"Could not resolve host: {domain or url}"}
    path = site / f"{name}.html"
    if not path.is_file() or "/" in name:
        return {"url": url, "error": "404 Not Found"}
    p = _Text(visible_only)
    p.feed(path.read_text())
    links = sorted({f"https://{domain}/{page_name(h)}".removesuffix("/index") for h in p.links
                    if not h.startswith(("http", "mailto:")) or domain_of(h) == domain})
    return {"url": f"https://{domain}/{name}".removesuffix("/index"), "title": p.title.strip(), "text": p.text(),
            "links": links}
