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
        library = Library(settings, "ja")
        article = Article("https://qgis.mierune.co.jp/posts/old", "保存する記事")
        library.toggle(article)
        restored = Library(settings, "ja")
        self.assertEqual(restored.find(article.url), article)
        self.assertTrue(restored.is_saved(article.url))
        restored.toggle(article)
        self.assertEqual(Library(settings, "ja").bookmarks, [])

    def test_invalid_records_are_ignored(self):
        settings = MemorySettings()
        settings.setValue(
            "qgislab/bookmarks",
            '[null, {}, {"url": "/posts/a", "title": "A", "categories": null}]',
        )
        self.assertEqual(len(Library(settings, "ja").bookmarks), 1)

    def test_only_the_current_languages_bookmarks_are_listed_but_all_are_kept(self):
        settings = MemorySettings()
        japanese = Article("https://qgis.mierune.co.jp/posts/a", "日本語")
        english = Article("https://qgis.mierune.co.jp/en/posts/a", "English")
        Library(settings, "ja").toggle(japanese)
        Library(settings, "en").toggle(english)
        self.assertEqual(Library(settings, "ja").bookmarks, [japanese])
        self.assertEqual(Library(settings, "en").bookmarks, [english])
        # Removing one never touches the other language's bookmark.
        Library(settings, "en").toggle(english)
        self.assertEqual(Library(settings, "en").bookmarks, [])
        self.assertEqual(Library(settings, "ja").bookmarks, [japanese])
