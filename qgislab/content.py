"""Extract QGIS LAB's article body into Qt's supported, inert HTML subset."""

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .articles import article_url, clean_title

MAX_PAGE_BYTES = 5 * 1024 * 1024
VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
OMIT = frozenset(
    "script style head nav footer form button input svg canvas object embed template noscript".split()
)
TAGS = frozenset(
    "p div span h1 h2 h3 h4 h5 h6 br hr strong b em i u s sub sup pre code blockquote ul ol li dl dt dd table thead tbody tfoot tr th td a small".split()
)


def web_url(value, base):
    try:
        result = urljoin(base, value)
        parts = urlsplit(result)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            return ""
        _ = parts.port  # Reject malformed ports before passing URLs to Qt.
        return result
    except (TypeError, ValueError):
        return ""


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        return "".join(
            child.text() if isinstance(child, Node) else child
            for child in self.children
        )


class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if len(self.stack) > 128:
            raise ValueError("記事HTMLの入れ子が深すぎます。")
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@dataclass(frozen=True)
class Content:
    title: str
    html: str
    images: dict


def extract_content(data, url):
    if len(data) > MAX_PAGE_BYTES:
        raise ValueError("記事のサイズが上限を超えています。")
    if not article_url(url):
        raise ValueError("QGIS LABの記事URLではありません。")
    parser = ArticleHTML()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    # The site embeds several <html>/<body> fragments in an <article>.
    # Target its explicit content container, never the whole page or a login/error page.
    article = next(
        (
            n
            for n in parser.root.walk()
            if n.tag == "article"
            and any(c.attrs.get("id") == "content" for c in n.walk())
        ),
        None,
    )
    if article is None:
        raise ValueError(
            "記事本文を見つけられませんでした。元の記事をブラウザで開いてください。"
        )
    body = next(n for n in article.walk() if n.attrs.get("id") == "content")
    heading = next((n for n in article.walk() if n.tag == "h1"), None)
    if heading is None or not heading.text().strip() or not body.text().strip():
        raise ValueError("記事のタイトルまたは本文を読み取れませんでした。")
    title = clean_title(heading.text())
    images = {}

    def render(node):
        if isinstance(node, str):
            return escape(node)
        tag, attrs = node.tag, node.attrs
        classes = set((attrs.get("class") or "").split())
        # The hydrated page includes a second, mobile-only summary and TOC.
        if tag in OMIT or "md-lg:hidden" in classes:
            return ""
        if tag in ("iframe", "video", "audio"):
            target = web_url(attrs["src"], url) if attrs.get("src") else ""
            if target and urlsplit(target).path == "/_embedded":
                target = web_url(
                    parse_qs(urlsplit(target).query).get("url", [""])[0], url
                )
            return (
                f'<p><a href="{escape(target, quote=True)}">{escape(target)}</a></p>'
                if target
                else "<p>この埋め込みコンテンツは「ブラウザで開く」からご覧ください。</p>"
            )
        if "callout-parent" in classes:
            caution = "caution" in classes
            text = "".join(
                render(child)
                for child in node.children
                if not (isinstance(child, Node) and child.tag == "img")
            )
            return (
                f'<table class="callout{" caution" if caution else ""}" width="100%" cellspacing="0" cellpadding="20"><tr>'
                f'<td width="28" valign="top"><b>{"⚠" if caution else "ⓘ"}</b></td>'
                f"<td>{text}</td></tr></table>"
            )
        if tag == "img":
            if "callout-icon" in (attrs.get("class") or "").split():
                label = attrs.get("alt") or (
                    "注意："
                    if (attrs.get("src") or "").endswith("/caution.svg")
                    else ""
                )
                return f"<strong>{escape(label)}</strong>"
            source = web_url(attrs.get("src") or attrs.get("data-src") or "", url)
            alt = escape(attrs.get("alt") or "記事の画像", quote=True)
            if not source or source == url:
                return f"<span>[{alt}]</span>"
            if len(images) >= 100:
                return f'<a href="{escape(source, quote=True)}">画像を開く: {alt}</a>'
            # Request PNG from the site's image CDN, so WebP plugins are not required.
            if urlsplit(source).hostname == "images.microcms-assets.io":
                parts = urlsplit(source)
                query = dict(parse_qsl(parts.query))
                query.update(fm="png", w="1200")
                source = urlunsplit(parts._replace(query=urlencode(query)))
            key = f"qgislab-image:/{len(images)}"
            images[key] = source
            return f'<img src="{key}" alt="{alt}">'
        inside = "".join(render(child) for child in node.children)
        anchor = attrs.get("id") or (attrs.get("name") if tag == "a" else "")
        prefix = f'<a name="{escape(anchor, quote=True)}">&#8203;</a>' if anchor else ""
        if anchor in ("content", "article-info"):
            prefix = ""
        # Qt does not implement flexbox or padded divs. Translate the site's
        # known article components into tables; never pass through arbitrary CSS.
        if "bg-qgis/10" in classes:
            return (
                '<table class="summary" width="100%" cellspacing="0" cellpadding="20"'
                f"><tr><td>{prefix}{inside}</td></tr></table>"
            )
        if "border-stone-500" in classes:
            return (
                '<table class="version" width="100%" cellspacing="0" cellpadding="16"'
                f"><tr><td>{inside}</td></tr></table>"
            )
        if "text-red-500" in classes:
            return f'<span class="warning">{inside}</span>'
        if "text-qgis" in classes and tag.startswith("h"):
            return f'<h3 class="summary-title">{inside}</h3>'
        if "font-bold" in classes and tag == "div":
            return f'<p class="intro"><strong>{inside}</strong></p>'
        if tag == "div" and any(n.tag == "time" for n in node.walk()):
            return f'<p class="dates">{inside}</p>'
        if tag == "figure":
            return f'<div class="figure">{prefix}{inside}</div>'
        if tag == "figcaption":
            return f'<p class="caption" align="center">{prefix}{inside}</p>'
        if tag in ("figure", "figcaption", "section", "header"):
            tag = "div"
        if tag not in TAGS:
            return prefix + inside
        attributes = ""
        if tag == "a":
            target = web_url(attrs.get("href", ""), url) if attrs.get("href") else ""
            if not target:
                return prefix + inside
            attributes = f' href="{escape(target, quote=True)}"'
            if "rounded-full" in classes:
                return (
                    '<p class="category"><span class="category-label">'
                    f"&nbsp;&nbsp;&nbsp;<a{attributes}>{inside}</a>&nbsp;&nbsp;&nbsp;</span></p>"
                )
            if "text-mierune" in classes:
                return f"<a{attributes}>{inside}</a>&nbsp;&nbsp;"
        if tag in ("td", "th"):
            for name in ("colspan", "rowspan"):
                value = attrs.get(name) or ""
                if value.isdigit() and 1 <= int(value) <= 100:
                    attributes += f' {name}="{value}"'
        if tag == "table":
            attributes = ' border="1" cellspacing="0" cellpadding="6" width="100%"'
        if tag == "ol" and (attrs.get("start") or "").isdigit():
            attributes = f' start="{int(attrs["start"])}"'
        if tag in VOID:
            return prefix + f"<{tag}>"
        return f"<{tag}{attributes}>{prefix}{inside}</{tag}>"

    dates = [
        (n.attrs.get("datetime") or "")[:10] for n in article.walk() if n.tag == "time"
    ]
    date_line = " · ".join(
        f"{label}: {date}" for label, date in zip(("公開", "更新"), dates) if date
    )
    header = next((n for n in article.walk() if n.tag == "header"), None)
    # The eyecatch is outside <header>; selecting header + body used to lose it.
    eyecatch = next(
        (
            n
            for n in article.walk()
            if n.tag == "img" and n.attrs.get("alt") == "eyecatch"
        ),
        None,
    )
    html = (
        (f'<p class="eyecatch">{render(eyecatch)}</p>' if eyecatch else "")
        + (
            render(header)
            if header
            else f"<h1>{escape(title)}</h1><p>{escape(date_line)}</p>"
        )
        + render(body)
    )
    html += (
        f'<hr><p>出典: <a href="{escape(url, quote=True)}">QGIS LAB by MIERUNE</a></p>'
    )
    return Content(title, html, images)
