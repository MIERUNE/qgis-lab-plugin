"""Paged article search; CMS fields and request replacement stay inside this module."""

import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from qgis.PyQt.QtCore import QObject, pyqtSignal

from .articles import SITE_URL, Article, date_text, plain_text
from .network import HttpGet

PAGE_SIZE = 12


@dataclass(frozen=True)
class SearchResult:
    articles: list
    total: int
    offset: int
    limit: int


def parse_results(data):
    try:
        payload = json.loads(data)
        contents = payload["contents"]
        total, offset, limit = (
            payload[key] for key in ("totalCount", "offset", "limit")
        )
        if (
            not isinstance(contents, list)
            or any(type(v) is not int for v in (total, offset, limit))
            or total < 0
            or offset < 0
            or not 1 <= limit <= 100
            or len(contents) > limit
        ):
            raise ValueError()
        articles = []
        for item in contents:
            identifier, title = item["id"], item["title"]
            if (
                not isinstance(identifier, str)
                or not identifier
                or not isinstance(title, str)
                or not title.strip()
            ):
                raise ValueError()
            category = item.get("category") or {}
            eyecatch = item.get("eyecatch")
            thumbnail = eyecatch.get("url", "") if isinstance(eyecatch, dict) else ""
            article = Article.from_dict(
                {
                    "url": SITE_URL + "posts/" + quote(identifier, safe=""),
                    "title": title,
                    "thumbnail": thumbnail,
                    "summary": plain_text(item.get("about") or ""),
                    "published": date_text(item.get("publishedAt") or ""),
                    "categories": [category["name"]] if category.get("name") else [],
                }
            )
            if article is None:
                raise ValueError()
            articles.append(article)
        return SearchResult(articles, total, offset, limit)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("記事検索の応答形式が正しくありません。") from error


class SearchClient(QObject):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.request = None

    def search(self, freeword="", page=1):
        self.cancel()
        query = urlencode(
            {
                "freeword": freeword.strip(),
                "page": page,
                "limit": PAGE_SIZE,
                "order": "newest",
            }
        )
        request = HttpGet(SITE_URL + "_api/posts?" + query, 5 * 1024 * 1024, self)
        self.request = request
        request.loaded.connect(lambda data: self._loaded(request, data))
        request.failed.connect(lambda error: self._failed(request, error))
        request.start()

    def _loaded(self, request, data):
        if request is not self.request:
            return
        self.request = None
        request.deleteLater()
        try:
            result = parse_results(data)
        except ValueError as error:
            self.failed.emit(str(error))
        else:
            self.loaded.emit(result)

    def _failed(self, request, error):
        if request is self.request:
            self.request = None
            request.deleteLater()
            self.failed.emit(error)

    def cancel(self):
        request, self.request = self.request, None
        if request is not None:
            request.cancel()
            request.deleteLater()
