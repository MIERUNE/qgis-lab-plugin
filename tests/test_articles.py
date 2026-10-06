import unittest

from qgislab.articles import (
    Article,
    article_language,
    article_url,
    home_url,
    post_url,
    site_language,
)


class ArticleTests(unittest.TestCase):
    def test_thumbnail_persistence_and_unsafe_urls(self):
        article = Article(
            "https://qgis.mierune.co.jp/posts/a",
            "A",
            thumbnail="https://images.microcms-assets.io/a.png",
        )
        self.assertEqual(Article.from_dict(article.to_dict()), article)
        for url in (
            "file:///tmp/image.png",
            "javascript:alert(1)",
            None,
            "http://[broken",
        ):
            self.assertEqual(
                Article.from_dict({**article.to_dict(), "thumbnail": url}).thumbnail, ""
            )

    def test_article_identity(self):
        self.assertEqual(
            article_url(
                "http://qgis.mierune.co.jp/posts/example/?utm_source=test#section"
            ),
            "https://qgis.mierune.co.jp/posts/example",
        )
        self.assertEqual(article_url("/posts/example"), article_url("/posts/example/"))
        for url in (
            "",
            "/posts",
            "/posts/",
            "/posts/../",
            "/posts/a/b",
            "javascript:alert(1)",
            "https://evil.test/posts/a",
            "https://qgis.mierune.co.jp.evil.test/posts/a",
            "https://user@qgis.mierune.co.jp/posts/a",
            "https://qgis.mierune.co.jp:bad/posts/a",
        ):
            with self.subTest(url=url):
                self.assertEqual(article_url(url), "")

    def test_english_articles_live_under_en(self):
        english = "https://qgis.mierune.co.jp/en/posts/example"
        self.assertEqual(article_url("/en/posts/example/?utm=a#s"), english)
        self.assertEqual(article_url(english, "en"), english)
        self.assertEqual(article_language(english), "en")
        self.assertEqual(article_language("https://qgis.mierune.co.jp/posts/a"), "ja")
        for url in ("/en/posts", "/en/posts/a/b", "/en/en/posts/a", "/fr/posts/a"):
            with self.subTest(url=url):
                self.assertEqual(article_url(url), "")

    def test_a_language_never_accepts_the_other_languages_articles(self):
        japanese = "https://qgis.mierune.co.jp/posts/example"
        english = "https://qgis.mierune.co.jp/en/posts/example"
        self.assertEqual(article_url(japanese, "ja"), japanese)
        self.assertEqual(article_url(english, "ja"), "")
        self.assertEqual(article_url(japanese, "en"), "")
        self.assertEqual(article_url(english, "en"), english)

    def test_site_language_follows_the_qgis_locale(self):
        for locale in ("ja", "ja_JP", "ja-JP", "JA"):
            with self.subTest(locale=locale):
                self.assertEqual(site_language(locale), "ja")
        for locale in ("en", "en_US", "fr", "fr_FR", "zh_CN", "jam", ""):
            with self.subTest(locale=locale):
                self.assertEqual(site_language(locale), "en")

    def test_home_and_post_urls_per_language(self):
        self.assertEqual(home_url("ja"), "https://qgis.mierune.co.jp/")
        self.assertEqual(home_url("en"), "https://qgis.mierune.co.jp/en/")
        self.assertEqual(
            post_url("a b", "ja"), "https://qgis.mierune.co.jp/posts/a%20b"
        )
        self.assertEqual(
            post_url("a/b", "en"), "https://qgis.mierune.co.jp/en/posts/a%2Fb"
        )

    def test_article_roundtrip_and_japanese_search(self):
        article = Article(
            "https://qgis.mierune.co.jp/posts/a",
            "地図の作成",
            "座標系を設定",
            categories=("QGIS",),
        )
        self.assertEqual(Article.from_dict(article.to_dict()), article)
        self.assertTrue(article.matches("地図 座標系"))
        self.assertIsNone(Article.from_dict({"url": "/posts/a", "title": None}))
