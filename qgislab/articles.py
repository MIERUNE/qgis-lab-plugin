"""Article metadata and identity, independent of QGIS and Qt."""

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import unquote, urljoin, urlsplit

SITE_URL = "https://qgis.mierune.co.jp/"


def article_url(url):
    """One bookmark per article, regardless of tracking query or section anchor."""
    try:
        parts = urlsplit(urljoin(SITE_URL, url))
        path = unquote(parts.path).rstrip("/")
        if (
            parts.scheme not in ("http", "https")
            or parts.hostname != "qgis.mierune.co.jp"
            or parts.username
            or parts.password
            or parts.port not in (None, 80, 443)
            or not re.fullmatch(r"/posts/[^/\s?#]+", path)
            or path.rsplit("/", 1)[-1] in (".", "..")
        ):
            return ""
        return SITE_URL.rstrip("/") + parts.path.rstrip("/")
    except (ValueError, TypeError):
        return ""


def plain_text(value):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", value)).split())


def clean_title(value):
    return plain_text(value).removesuffix(" - QGIS LAB by MIERUNE").strip()


def date_text(value):
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            return (
                datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
            )
        except (TypeError, ValueError):
            return ""


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    summary: str = ""
    published: str = ""
    categories: tuple = ()
    thumbnail: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            return None
        url = article_url(value.get("url", ""))
        title = value.get("title")
        if not url or not isinstance(title, str) or not title.strip():
            return None
        categories = value.get("categories", [])
        thumbnail = value.get("thumbnail", "")
        try:
            parts = urlsplit(thumbnail) if isinstance(thumbnail, str) else None
            if (
                not parts
                or parts.scheme not in ("https", "http")
                or not parts.hostname
                or parts.username
                or parts.password
            ):
                thumbnail = ""
        except ValueError:
            thumbnail = ""
        return cls(
            url,
            clean_title(title),
            plain_text(str(value.get("summary", ""))),
            str(value.get("published", "")),
            tuple(c for c in categories if isinstance(c, str))
            if isinstance(categories, (list, tuple))
            else (),
            thumbnail,
        )

    def matches(self, query):
        haystack = " ".join((self.title, self.summary, *self.categories)).casefold()
        return all(word in haystack for word in query.casefold().split())
