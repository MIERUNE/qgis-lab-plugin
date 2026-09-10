import unittest

from qgislab.articles import Article
from qgislab.storage import Library


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


class LibraryTests(unittest.TestCase):
    def test_bookmarks_survive_restart(self):
        settings = MemorySettings()
        library = Library(settings)
        article = Article("https://qgis.mierune.co.jp/posts/old", "保存する記事")
        library.toggle(article)
        restored = Library(settings)
        self.assertEqual(restored.find(article.url), article)
        self.assertTrue(restored.is_saved(article.url))
        restored.toggle(article)
        self.assertEqual(Library(settings).bookmarks, [])

    def test_invalid_records_are_ignored(self):
        settings = MemorySettings()
        settings.setValue(
            "qgislab/bookmarks",
            '[null, {}, {"url": "/posts/a", "title": "A", "categories": null}]',
        )
        self.assertEqual(len(Library(settings).bookmarks), 1)
