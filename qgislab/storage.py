"""Persist bookmarked articles."""

import json

from .articles import Article, article_language


class Library:
    """Accept QSettings (or an equivalent store) without leaking its keys to the UI.

    Bookmarks of both languages are kept, so switching QGIS's language back and
    forth loses nothing, but only those in the current language are listed.
    """

    def __init__(self, settings, language):
        self.settings = settings
        self.language = language
        self._articles = self._read("bookmarks")

    @property
    def bookmarks(self):
        return [a for a in self._articles if article_language(a.url) == self.language]

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
        return any(a.url == url for a in self._articles)

    def toggle(self, article):
        if self.is_saved(article.url):
            self._articles = [a for a in self._articles if a.url != article.url]
        else:
            self._articles.insert(0, article)
        self._write("bookmarks", self._articles)

    def find(self, url):
        return next((a for a in self._articles if a.url == url), None)
