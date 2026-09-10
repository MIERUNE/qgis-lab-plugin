import unittest

from qgislab.content import extract_content, web_url

URL = "https://qgis.mierune.co.jp/posts/example"


def page(body):
    return (
        "<html><head><title>Site</title></head><nav>Navigation</nav>"
        '<article><h1>記事のタイトル</h1><time datetime="2026-09-09T00:00:00Z">Date</time>'
        '<div id="content">' + body + "</div><footer>Footer</footer></article></html>"
    ).encode()


class ContentTests(unittest.TestCase):
    def test_body_structure_and_chrome_exclusion(self):
        content = extract_content(
            page(
                '<html><head></head><body><h2 id="見出し">見出し</h2>'
                "<p>本文<strong>重要</strong></p><pre><code>x &lt; 3\nprint(x)</code></pre>"
                '<table><tr><th>項目</th><td colspan="2">値</td></tr></table>'
                "<ul><li>項目</li></ul></body></html>"
            ),
            URL,
        )
        self.assertEqual(content.title, "記事のタイトル")
        self.assertIn("2026-09-09", content.html)
        self.assertIn('<a name="見出し">', content.html)
        self.assertIn("<strong>重要</strong>", content.html)
        self.assertIn("x &lt; 3\nprint(x)", content.html)
        self.assertIn('colspan="2"', content.html)
        self.assertNotIn("Navigation", content.html)
        self.assertNotIn("Footer", content.html)

    def test_removes_active_content_and_local_resource_urls(self):
        content = extract_content(
            page(
                '<p style="background-image:url(file:///secret)" onclick="alert(1)">Safe</p>'
                "<script>alert(2)</script><style>evil</style><form>Hidden</form>"
                '<img src="file:///etc/passwd"><a href="javascript:alert(3)">Link</a>'
                '<a href="/posts/next#section">Next</a>'
            ),
            URL,
        )
        for value in (
            "onclick",
            "background-image",
            "<script",
            "<style",
            "<form",
            "alert(",
            "file:",
        ):
            self.assertNotIn(value, content.html)
        self.assertEqual(content.images, {})
        self.assertIn("https://qgis.mierune.co.jp/posts/next#section", content.html)

    def test_images_are_inert_resources_and_cdn_uses_png(self):
        content = extract_content(
            page(
                '<p>Text</p><img src="https://images.microcms-assets.io/a.png?w=1080&amp;fm=webp" alt="A&amp;B">'
                '<img src="/image.png" alt="Local image">'
            ),
            URL,
        )
        self.assertIn("qgislab-image:/0", content.html)
        self.assertIn('alt="A&amp;B"', content.html)
        self.assertIn("fm=png", content.images["qgislab-image:/0"])
        self.assertEqual(
            content.images["qgislab-image:/1"], "https://qgis.mierune.co.jp/image.png"
        )
        self.assertNotIn('<img src="https:', content.html)

    def test_embedded_cards_become_article_links(self):
        content = extract_content(
            page(
                '<p>Related</p><iframe src="/_embedded?url=https%3A%2F%2Fqgis.mierune.co.jp%2Fposts%2Fother"></iframe>'
            ),
            URL,
        )
        self.assertIn('href="https://qgis.mierune.co.jp/posts/other"', content.html)
        self.assertIn(">https://qgis.mierune.co.jp/posts/other</a>", content.html)
        self.assertNotIn("関連コンテンツを開く", content.html)
        self.assertNotIn("<iframe", content.html)

    def test_embedded_url_label_is_escaped_and_matches_the_destination(self):
        content = extract_content(
            page(
                '<p>Video</p><iframe src="https://example.com/video?a=1&amp;b=2"></iframe>'
            ),
            URL,
        )
        self.assertIn(
            '<a href="https://example.com/video?a=1&amp;b=2">'
            "https://example.com/video?a=1&amp;b=2</a>",
            content.html,
        )

    def test_rejects_unrecognized_or_incomplete_pages(self):
        for data in (b"<html>404</html>", b"<article><h1>A</h1></article>", page("")):
            with self.assertRaises(ValueError):
                extract_content(data, URL)

    def test_url_validation(self):
        for value in (
            "javascript:1",
            "file:///etc/passwd",
            "data:text/html,hello",
            "https://host:bad/path",
            "https://user:password@example.com",
        ):
            self.assertEqual(web_url(value, URL), "")
        self.assertEqual(web_url("#heading", URL), URL + "#heading")

    def test_site_article_components_keep_their_structure_without_duplicate_intro(self):
        content = extract_content(
            (
                '<article><div><img src="/hero.png" alt="eyecatch"></div>'
                '<header><h1>Title</h1><div class="hidden lg:block font-bold">概要</div>'
                '<div class="md-lg:hidden">概要<button>目次</button></div>'
                '<div class="bg-qgis/10"><h3 class="text-qgis">この記事でわかること</h3>'
                '<div id="article-info"><ul><li>学べること</li></ul></div></div>'
                '<div class="border-stone-500">QGIS 4.2 <span class="text-red-500">注意</span></div>'
                '</header><div id="content"><h2 id="section">本文</h2>'
                '<div class="callout-parent info"><img class="callout-icon" src="/callout/info.svg">'
                '<div class="callout-text">補足<strong>重要</strong></div></div>'
                '<figure><img src="/figure.png"><figcaption>図の説明</figcaption></figure>'
                "</div></article>"
            ).encode(),
            URL,
        )
        self.assertLess(
            content.html.index('class="eyecatch"'), content.html.index("<h1>")
        )
        self.assertEqual(content.html.count("概要"), 1)
        self.assertNotIn("目次", content.html)
        self.assertIn('class="summary"', content.html)
        self.assertIn('class="version"', content.html)
        self.assertIn('class="callout"', content.html)
        self.assertIn("<strong>重要</strong>", content.html)
        self.assertIn('class="caption" align="center">図の説明', content.html)
        self.assertEqual(
            list(content.images.values()),
            [
                "https://qgis.mierune.co.jp/hero.png",
                "https://qgis.mierune.co.jp/figure.png",
            ],
        )

    def test_keeps_article_header_guidance_and_converts_callout_icons(self):
        data = (
            "<article><header><h1>Title</h1><p>この記事はQGIS 3.44を使用しています。</p></header>"
            '<div id="content"><p>本文</p><img class="callout-icon" src="/callout/caution.svg">'
            "<p>注意の本文</p></div></article>"
        ).encode()
        content = extract_content(data, URL)
        self.assertIn("QGIS 3.44", content.html)
        self.assertIn("注意：", content.html)
        self.assertEqual(content.images, {})
