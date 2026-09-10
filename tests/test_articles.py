import unittest

from qgislab.articles import Article, article_url


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
