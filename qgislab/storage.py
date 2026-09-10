"""Persist bookmarked articles."""

import json

from .articles import Article


class Library:
    """Accept QSettings (or an equivalent store) without leaking its keys to the UI."""

    def __init__(self, settings):
        self.settings = settings
        self.bookmarks = self._read("bookmarks")

    def _read(self, key):
        try:
            rows = json.loads(self.settings.value("qgislab/" + key, "[]"))
        except (TypeError, ValueError):
            return []
        if not isinstance(rows, list):
            return []
        result = {}
        for row in rows:
            article = Article.from_dict(row)
            if article:
                result.setdefault(article.url, article)
        return list(result.values())

    def _write(self, key, articles):
        self.settings.setValue(
            "qgislab/" + key,
            json.dumps([a.to_dict() for a in articles], ensure_ascii=False),
        )
        self.settings.sync()

    def is_saved(self, url):
        return any(a.url == url for a in self.bookmarks)

    def toggle(self, article):
        if self.is_saved(article.url):
            self.bookmarks = [a for a in self.bookmarks if a.url != article.url]
        else:
            self.bookmarks.insert(0, article)
        self._write("bookmarks", self.bookmarks)

    def find(self, url):
        return next((a for a in self.bookmarks if a.url == url), None)
