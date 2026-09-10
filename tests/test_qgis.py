"""Real Qt widgets, settings, network signals and plugin lifecycle; no public network."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

try:
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import (
        QEvent,
        QObject,
        QSettings,
        QSize,
        Qt,
        QUrl,
        pyqtSignal,
    )
    from qgis.PyQt.QtNetwork import QNetworkReply
    from qgis.PyQt.QtWidgets import QMainWindow
except ImportError:
    if os.environ.get("QGISLAB_REQUIRE_QGIS"):
        raise
    raise unittest.SkipTest("QGIS Python environment is required") from None

from qgislab.articles import Article  # noqa: E402
from qgislab.dock import LabDock  # noqa: E402
from qgislab.network import HttpGet  # noqa: E402
from qgislab.plugin import QgisLabPlugin  # noqa: E402
from qgislab.reader import ArticleReader  # noqa: E402
from qgislab.search import SearchClient, SearchResult, parse_results  # noqa: E402

APP = QgsApplication.instance() or QgsApplication([], False)


class Iface:
    def __init__(self):
        self.window = QMainWindow()
        self.actions = []

    def mainWindow(self):
        return self.window

    def addPluginToWebMenu(self, name, action):
        self.actions.append(action)

    def removePluginWebMenu(self, name, action):
        self.actions.remove(action)

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


class DockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = QSettings(
            self.temp.name + "/settings.ini", QSettings.Format.IniFormat
        )
        self.iface = Iface()
        self.search_mock = patch("qgislab.search.HttpGet", PendingGet)
        self.search_mock.start()
        self.dock = LabDock(self.iface, self.settings)
        self.articles = [
            Article(
                "https://qgis.mierune.co.jp/posts/one",
                "地図を作る",
                "座標系の設定",
                "2026-09-09",
            ),
            Article(
                "https://qgis.mierune.co.jp/posts/two",
                "ラスタ解析",
                "標高を表示",
                "2026-09-08",
            ),
        ]
        self.dock._search_loaded(SearchResult(self.articles, 2, 0, 12))

    def tearDown(self):
        self.dock.shutdown()
        self.dock.close()
        self.dock.deleteLater()
        self.iface.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()
        self.search_mock.stop()

    def test_search_selection_bookmark_and_restart(self):
        with patch.object(self.dock.reader, "open", side_effect=self.set_url):
            self.dock.search.setText("座標系")
            self.dock.search_timer.stop()
            self.dock._search_loaded(SearchResult(self.articles[:1], 1, 0, 12))
            self.assertEqual(self.dock.list.count(), 1)
            self.dock.list.setCurrentRow(0)
            self.assertTrue(self.dock.save_button.isEnabled())
            self.dock.save_button.click()
            self.assertTrue(self.dock.library.is_saved(self.articles[0].url))
            self.dock.tabs.setCurrentIndex(1)
            self.assertEqual(self.dock.list.count(), 1)
            from qgislab.storage import Library

            self.assertEqual(
                Library(
                    QSettings(self.settings.fileName(), QSettings.Format.IniFormat)
                ).bookmarks,
                [self.articles[0]],
            )
            self.dock.save_button.click()
            self.assertEqual(self.dock.list.count(), 0)
            self.assertFalse(self.dock.empty.isHidden())

    def set_url(self, url):
        self.dock.reader.current_url = url
        self.dock.reader.changed.emit()

    def test_web_navigation_saves_articles_outside_results(self):
        self.dock.reader.current_title = "新しい記事 - QGIS LAB by MIERUNE"
        self.set_url("https://qgis.mierune.co.jp/posts/new?utm=a#section")
        self.dock.save_button.click()
        self.assertEqual(self.dock.library.bookmarks[0].title, "新しい記事")
        self.assertEqual(
            self.dock.library.bookmarks[0].url, "https://qgis.mierune.co.jp/posts/new"
        )
        self.set_url("https://qgis.mierune.co.jp/posts")
        self.assertFalse(self.dock.save_button.isEnabled())

    def test_search_results_do_not_change_home(self):
        home = self.dock.reader.toHtml()
        self.dock.search.setText("地図")
        self.dock._search_loaded(SearchResult(self.articles[:1], 1, 0, 12))
        self.assertEqual(self.dock.reader.toHtml(), home)
        self.dock.search.clear()
        self.dock._search_loaded(SearchResult([], 24, 12, 12))
        self.assertEqual(self.dock.reader.toHtml(), home)
        self.dock._search_loaded(SearchResult(self.articles[:1], 1, 0, 12))
        self.assertEqual(self.dock.reader.toHtml(), home)

    def test_search_paging_failure_and_bookmark_tab(self):
        from urllib.parse import parse_qs, urlsplit

        self.dock.search.setText("地図 & QGIS")
        self.assertTrue(self.dock.search_timer.isActive())
        self.dock.search.returnPressed.emit()
        query = parse_qs(urlsplit(PendingGet.calls[-1].url).query)
        self.assertEqual(query["freeword"], ["地図 & QGIS"])
        self.assertFalse(self.dock.search_timer.isActive())
        self.dock._search_loaded(SearchResult(self.articles, 25, 0, 12))
        self.dock.next_page.click()
        self.assertEqual(
            parse_qs(urlsplit(PendingGet.calls[-1].url).query)["page"], ["2"]
        )
        PendingGet.calls[-1].failed.emit("HTTP 502")
        self.assertIn("502", self.dock.search_status.text())
        self.assertEqual(self.dock.search_page, 1)
        self.assertTrue(self.dock.search_retry.isEnabled())
        self.dock.search_retry.click()
        request = PendingGet.calls[-1]
        self.dock.tabs.setCurrentIndex(1)
        self.assertFalse(request.cancelled)
        self.assertFalse(self.dock.search_timer.isActive())
        self.assertTrue(self.dock.search_pending)
        count = len(PendingGet.calls)
        request.loaded.emit(
            b'{"contents": [], "totalCount": 0, "offset": 0, "limit": 12}'
        )
        self.assertFalse(self.dock.search_pending)
        self.dock.tabs.setCurrentIndex(0)
        self.assertEqual(len(PendingGet.calls), count)
        self.assertFalse(self.dock.search_timer.isActive())

    def test_tab_switch_preserves_results_page_and_query_without_request(self):
        self.dock.search.setText("地図")
        self.dock.search.returnPressed.emit()
        self.dock._search_loaded(SearchResult(self.articles, 30, 12, 12))
        result = self.dock.results
        count = len(PendingGet.calls)
        for _ in range(3):
            self.dock.tabs.setCurrentIndex(1)
            self.dock.tabs.setCurrentIndex(0)
        self.assertIs(self.dock.results, result)
        self.assertEqual(self.dock.search_page, 2)
        self.assertEqual(self.dock.search.text(), "地図")
        self.assertEqual(self.dock.list.count(), 2)
        self.assertEqual(len(PendingGet.calls), count)
        self.assertFalse(self.dock.search_timer.isActive())

    def test_pending_query_completes_while_saved_tab_is_open(self):
        self.dock.search.setText("地図")
        self.dock.tabs.setCurrentIndex(1)
        self.assertTrue(self.dock.search_timer.isActive())
        self.dock.search_timer.timeout.emit()
        request = PendingGet.calls[-1]
        request.loaded.emit(
            b'{"contents": [], "totalCount": 0, "offset": 0, "limit": 12}'
        )
        self.assertFalse(self.dock.search_pending)
        count = len(PendingGet.calls)
        self.dock.tabs.setCurrentIndex(0)
        self.assertEqual(len(PendingGet.calls), count)
        self.assertFalse(self.dock.search_timer.isActive())

    def test_widget_can_render(self):
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.iface.window.resize(1150, 800)
        self.iface.window.show()
        self.dock.show()
        APP.processEvents()
        self.assertGreater(self.dock.reader.viewport().width(), 300)
        self.assertFalse(self.dock.grab().isNull())

    def test_saved_tab_hides_search_without_filtering_bookmarks(self):
        for article in self.articles:
            self.dock.library.toggle(article)
        self.dock.search.setText("no matching article")
        self.dock.tabs.setCurrentIndex(1)
        self.assertTrue(self.dock.search_controls.isHidden())
        self.assertEqual(self.dock.list.count(), 2)
        self.dock.tabs.setCurrentIndex(0)
        self.assertFalse(self.dock.search_controls.isHidden())
        self.assertEqual(self.dock.search.text(), "no matching article")

    def test_sidebar_is_visible_despite_legacy_preference(self):
        self.settings.setValue("qgislab/sidebar_visible", False)
        restored = LabDock(self.iface, self.settings)
        self.assertFalse(restored.sidebar.isHidden())
        restored.shutdown()
        restored.deleteLater()

    def test_lifecycle_uses_one_dock_and_unloads(self):
        plugin = QgisLabPlugin(self.iface)
        plugin.initGui()
        with patch.object(LabDock, "start"):
            plugin.run()
            first = plugin.dock
            plugin.run()
            self.assertIs(plugin.dock, first)
        plugin.unload()
        self.assertIsNone(plugin.dock)
        self.assertEqual(self.iface.actions, [])


class Reply(QObject):
    readyRead = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.data = b""
        self.code = 200
        self.aborted = False

    def readAll(self):
        data, self.data = self.data, b""
        return data

    def attribute(self, key):
        return self.code

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def errorString(self):
        return "HTTP error"

    def abort(self):
        self.aborted = True
        self.finished.emit()


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.client = HttpGet("https://example.com/articles", 5 * 1024 * 1024)
        self.reply = Reply()
        self.mock = patch("qgislab.network.QgsNetworkAccessManager")
        self.manager = self.mock.start().instance.return_value
        self.manager.get.return_value = self.reply
        self.loaded, self.failed = [], []
        self.client.loaded.connect(self.loaded.append)
        self.client.failed.connect(self.failed.append)
        self.client.start()

    def tearDown(self):
        self.client.cancel()
        self.mock.stop()

    def test_success_and_no_overlapping_requests(self):
        self.client.start()
        self.manager.get.assert_called_once()
        self.reply.data = b"article response"
        self.reply.readyRead.emit()
        self.reply.finished.emit()
        self.assertEqual(self.loaded, [b"article response"])
        self.assertEqual(self.failed, [])
        self.assertIsNone(self.client.reply)
        self.assertFalse(self.client.timer.isActive())

    def test_http_failure(self):
        self.reply.code = 503
        self.reply.finished.emit()
        self.assertEqual(self.loaded, [])
        self.assertEqual(len(self.failed), 1)

    def test_timeout_and_size_limit(self):
        self.client.timer.timeout.emit()
        self.assertTrue(self.reply.aborted)
        self.assertIn("タイムアウト", self.failed[0])

    def test_size_limit(self):
        self.reply.data = b"x" * (5 * 1024 * 1024 + 1)
        self.reply.readyRead.emit()
        self.assertTrue(self.reply.aborted)
        self.assertEqual(len(self.failed), 1)

    def test_unload_aborts_without_emitting_failure(self):
        self.client.cancel()
        self.assertTrue(self.reply.aborted)
        self.assertEqual(self.failed, [])


class PendingGet(QObject):
    loaded = pyqtSignal(bytes)
    failed = pyqtSignal(str)
    calls = []

    def __init__(self, url, byte_limit, parent=None):
        super().__init__(parent)
        self.url = url
        self.cancelled = False
        self.calls.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class ThumbnailTests(unittest.TestCase):
    def test_visible_only_cancellation_cache_and_failures(self):
        from qgis.PyQt.QtCore import QBuffer, QIODevice
        from qgis.PyQt.QtGui import QImage
        from qgis.PyQt.QtWidgets import QListWidgetItem

        from qgislab.thumbnails import ArticleList

        with patch("qgislab.thumbnails.HttpGet", PendingGet):
            widget = ArticleList()
            widget.resize(300, 240)
            for i in range(30):
                item = QListWidgetItem(str(i))
                item.setSizeHint(QSize(280, 80))
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    (
                        Article(
                            f"https://qgis.mierune.co.jp/posts/{i}",
                            str(i),
                            thumbnail=f"https://images.microcms-assets.io/{i}.png",
                        ),
                        False,
                    ),
                )
                widget.addItem(item)
            widget._load_visible()
            self.assertEqual(len(widget._requests), 0)
            widget.show()
            APP.processEvents()
            widget._load_visible()
            self.assertGreater(len(widget._requests), 0)
            self.assertLessEqual(len(widget._requests), 4)
            first_url, first = next(iter(widget._requests.items()))
            self.assertIn("w=320", first.url)
            picture = QImage(640, 360, QImage.Format.Format_RGB32)
            picture.fill(Qt.GlobalColor.red)
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            picture.save(buffer, "PNG")
            first.loaded.emit(bytes(buffer.data()))
            self.assertEqual(widget.thumbnail(first_url).width(), 320)
            widget._load_visible()
            self.assertNotIn(first_url, widget._requests)
            old = list(widget._requests.values())
            widget.scrollToBottom()
            widget._load_visible()
            self.assertTrue(all(request.cancelled for request in old))
            for request in old:
                request.loaded.emit(bytes(buffer.data()))
            self.assertEqual(len(widget._cache), 1)
            url, request = next(iter(widget._requests.items()))
            request.loaded.emit(b"broken image")
            self.assertIn(url, widget._cache)
            self.assertIsNone(widget.thumbnail(url))
            widget.hide()
            self.assertEqual(widget._requests, {})
            widget.shutdown()
            widget.deleteLater()
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class SearchTests(unittest.TestCase):
    def test_parse_api_metadata_and_invalid_responses(self):
        payload = {
            "contents": [
                {
                    "id": "example",
                    "title": "記事",
                    "about": "<p>概要</p>",
                    "publishedAt": "2026-09-10T00:00:00Z",
                    "category": {"name": "入門"},
                }
            ],
            "totalCount": 25,
            "offset": 12,
            "limit": 12,
        }
        result = parse_results(json.dumps(payload).encode())
        self.assertEqual(
            result.articles[0],
            Article(
                "https://qgis.mierune.co.jp/posts/example",
                "記事",
                "概要",
                "2026-09-10",
                ("入門",),
            ),
        )
        self.assertEqual((result.total, result.offset, result.limit), (25, 12, 12))
        for data in (
            b"{}",
            b"not json",
            b'{"contents": [], "totalCount": 1, "offset": 0, "limit": 0}',
        ):
            with self.assertRaises(ValueError):
                parse_results(data)

    def test_replaced_search_ignores_late_success_and_failure(self):
        with patch("qgislab.search.HttpGet", PendingGet):
            client = SearchClient()
            results, errors = [], []
            client.loaded.connect(results.append)
            client.failed.connect(errors.append)
            client.search("old")
            old = PendingGet.calls[-1]
            client.search("new")
            new = PendingGet.calls[-1]
            self.assertTrue(old.cancelled)
            response = b'{"contents": [], "totalCount": 0, "offset": 0, "limit": 12}'
            old.loaded.emit(response)
            old.failed.emit("late failure")
            self.assertEqual(results, [])
            self.assertEqual(errors, [])
            new.loaded.emit(response)
            self.assertEqual(len(results), 1)
            client.search()
            PendingGet.calls[-1].loaded.emit(b"invalid")
            self.assertEqual(len(errors), 1)
            client.cancel()
            client.deleteLater()


PAGE = b'<article><h1>Article title</h1><div id="content"><h2 id="section">Heading</h2><p>Full article body</p></div></article>'
PAGE_WITH_IMAGE = PAGE.replace(
    b"</div>", b'<p><img src="https://example.com/a.png" alt="Example"></p></div>'
)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        PendingGet.calls = []
        self.mock = patch("qgislab.reader.HttpGet", PendingGet)
        self.mock.start()
        self.reader = ArticleReader()
        self.reader.resize(720, 600)
        self.reader.show()
        APP.processEvents()

    def tearDown(self):
        self.reader.shutdown()
        self.reader.close()
        self.reader.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.mock.stop()

    def test_external_and_unsafe_navigation(self):
        with patch.object(self.reader, "_external") as external:
            self.reader.open("javascript:alert(1)")
            self.reader.open("file:///tmp/a")
            external.assert_not_called()
            self.reader.open("https://example.com/")
            self.reader.open("https://qgis.mierune.co.jp/posts")
            self.assertEqual(external.call_count, 2)
        self.assertEqual(PendingGet.calls, [])

    def test_home_website_link_opens_browser_without_leaving_home(self):
        home = self.reader.toHtml()
        self.assertIn('href="https://qgis.mierune.co.jp/"', home)
        with patch.object(self.reader, "_external") as external:
            self.reader.anchorClicked.emit(QUrl("https://qgis.mierune.co.jp/"))
            external.assert_called_once_with("https://qgis.mierune.co.jp/")
        self.assertEqual(self.reader.toHtml(), home)
        self.assertEqual(PendingGet.calls, [])

    def test_body_navigation_and_home(self):
        self.reader.open("https://qgis.mierune.co.jp/posts/a")
        first = PendingGet.calls[-1]
        first.loaded.emit(PAGE)
        self.assertIn("Full article body", self.reader.toPlainText())
        self.assertEqual(self.reader.current_title, "Article title")
        self.reader.anchorClicked.emit(QUrl("https://qgis.mierune.co.jp/posts/b"))
        self.assertTrue(self.reader.can_go_back)
        self.reader.back()
        self.assertTrue(PendingGet.calls[-2].cancelled)
        self.assertTrue(self.reader.can_go_forward)
        self.assertEqual(self.reader.current_url, "https://qgis.mierune.co.jp/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE)
        count = len(PendingGet.calls)
        self.reader.anchorClicked.emit(QUrl("#section"))
        self.assertEqual(len(PendingGet.calls), count)
        self.reader.forward()
        self.assertEqual(self.reader.current_url, "https://qgis.mierune.co.jp/posts/b")
        self.reader.home()
        self.assertEqual(self.reader.current_url, "https://qgis.mierune.co.jp/")
        self.assertIn("記事を選択してください", self.reader.toPlainText())

    def test_home_shows_guidance_and_installed_version_without_network(self):
        from configparser import ConfigParser
        from pathlib import Path

        metadata = ConfigParser()
        metadata.read(
            Path(__file__).resolve().parents[1] / "metadata.txt", encoding="utf-8"
        )
        self.assertIn("記事を選択してください", self.reader.toPlainText())
        self.assertIn("このプラグインについて", self.reader.toPlainText())
        self.assertIn(
            "バージョン " + metadata["general"]["version"], self.reader.toPlainText()
        )
        self.assertFalse(self.reader._logo.isNull())
        self.assertEqual(PendingGet.calls, [])

    def test_old_responses_cannot_replace_current_page(self):
        self.reader.open("/posts/a")
        first = PendingGet.calls[-1]
        self.reader.open("/posts/b")
        second = PendingGet.calls[-1]
        self.assertTrue(first.cancelled)
        first.loaded.emit(PAGE)
        self.assertNotIn("Full article body", self.reader.toPlainText())
        second.loaded.emit(PAGE.replace(b"Article title", b"Second"))
        self.assertEqual(self.reader.current_title, "Second")

    def test_failure_clears_previous_body_and_allows_retry(self):
        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE)
        self.reader.open("/posts/b")
        PendingGet.calls[-1].failed.emit("Offline <error>")
        self.assertNotIn("Full article body", self.reader.toPlainText())
        self.assertIn("Offline <error>", self.reader.toPlainText())
        self.reader.reload()
        PendingGet.calls[-1].loaded.emit(PAGE)
        self.assertIn("Full article body", self.reader.toPlainText())

    def test_malformed_page_reports_error(self):
        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(b"<html>login</html>")
        self.assertIn("本文を見つけられません", self.reader.toPlainText())

    def test_images_use_network_and_resize_without_reloading_article(self):
        from qgis.PyQt.QtCore import QBuffer, QIODevice
        from qgis.PyQt.QtGui import QImage, QTextDocument

        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE_WITH_IMAGE)
        request = PendingGet.calls[-1]
        self.assertEqual(request.url, "https://example.com/a.png")
        image = QImage(1000, 500, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        request.loaded.emit(bytes(buffer.data()))
        APP.processEvents()
        resource = self.reader.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl("qgislab-image:/0")
        )
        self.assertLess(resource.width(), 720)
        self.assertAlmostEqual(resource.width() / resource.height(), 2, places=1)
        count = len(PendingGet.calls)
        self.reader.resize(400, 600)
        self.reader._resize_images()
        resource = self.reader.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl("qgislab-image:/0")
        )
        self.assertLess(resource.width(), 400)
        self.assertEqual(len(PendingGet.calls), count)
        self.assertIsNone(
            self.reader.loadResource(
                QTextDocument.ResourceType.ImageResource, QUrl("file:///tmp/secret")
            )
        )

    def test_broken_images_keep_readable_text(self):
        messages = []
        self.reader.message.connect(messages.append)
        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE_WITH_IMAGE)
        PendingGet.calls[-1].loaded.emit(b"not an image")
        self.assertIn("Full article body", self.reader.toPlainText())
        self.assertIn("画像 1 枚を表示できません", messages[-1])

    def test_new_navigation_cancels_image_requests(self):
        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE_WITH_IMAGE)
        image = PendingGet.calls[-1]
        self.reader.open("/posts/b")
        self.assertTrue(image.cancelled)
        image.loaded.emit(b"late")
        self.assertEqual(self.reader._image_errors, 0)

    def test_image_concurrency_is_bounded(self):
        self.reader.open("/posts/a")
        page = PAGE.replace(
            b"</div>", b'<img src="https://example.com/a.png">' * 10 + b"</div>"
        )
        PendingGet.calls[-1].loaded.emit(page)
        self.assertEqual(len(self.reader._image_requests), 4)
        self.assertEqual(len(self.reader._queue), 6)

    def test_heading_anchor_actually_scrolls(self):
        self.reader.open("/posts/a")
        page = PAGE.replace(
            b'<h2 id="section">', b"<p>Paragraph</p>" * 100 + b'<h2 id="section">'
        )
        PendingGet.calls[-1].loaded.emit(page)
        APP.processEvents()
        self.assertEqual(self.reader.verticalScrollBar().value(), 0)
        self.reader.open("#section")
        self.assertGreater(self.reader.verticalScrollBar().value(), 0)

    def test_site_typography_survives_qt_html_import_and_wide_layout(self):
        from qgis.PyQt.QtGui import QTextBlockFormat

        self.reader.resize(1200, 600)
        APP.processEvents()
        self.reader.open("/posts/a")
        PendingGet.calls[-1].loaded.emit(PAGE)
        heading = self.reader.document().find("Heading").charFormat()
        self.assertEqual(heading.font().pixelSize(), 28)
        paragraph = self.reader.document().find("Full article body").blockFormat()
        self.assertEqual(paragraph.lineHeight(), 32)
        self.assertEqual(
            QTextBlockFormat.LineHeightTypes(paragraph.lineHeightType()),
            QTextBlockFormat.LineHeightTypes.MinimumHeight,
        )
        frame = self.reader.document().rootFrame().frameFormat()
        column = (
            self.reader.viewport().width() - frame.leftMargin() - frame.rightMargin()
        )
        self.assertLessEqual(column, 738)
        self.reader.resize(400, 600)
        APP.processEvents()
        self.reader._resize_images()
        self.assertEqual(self.reader.horizontalScrollBar().maximum(), 0)

    def test_theme_switch_preserves_article_position_and_inherited_palette(self):
        from qgis.PyQt.QtGui import QColor, QPalette

        self.reader.open("/posts/a")
        page = PAGE.replace(
            b"</div>",
            b'<div class="bg-qgis/10"><h3 class="text-qgis">Summary</h3><p>Details</p></div>'
            + b"<p>More text</p>" * 50
            + b"</div>",
        )
        PendingGet.calls[-1].loaded.emit(page)
        self.reader.verticalScrollBar().setValue(100)
        requests = len(PendingGet.calls)
        for base, text, summary in (
            ("#202020", "#eeeeee", "#2c3423"),
            ("#ffffff", "#202020", "#f2f6e9"),
        ):
            palette = self.reader.palette()
            palette.setColor(QPalette.ColorRole.Base, QColor(base))
            palette.setColor(QPalette.ColorRole.Text, QColor(text))
            self.reader.setPalette(palette)
            APP.processEvents()
            self.assertEqual(
                self.reader.palette().color(QPalette.ColorRole.Base).name(), base
            )
            self.assertEqual(
                self.reader.document()
                .find("Full article body")
                .charFormat()
                .foreground()
                .color()
                .name(),
                text,
            )
            frames = self.reader.document().rootFrame().childFrames()
            self.assertEqual(
                frames[0].frameFormat().background().color().name(), summary
            )
            self.assertEqual(self.reader.verticalScrollBar().value(), 100)
            self.assertEqual(len(PendingGet.calls), requests)
            self.assertEqual(
                self.reader.current_url, "https://qgis.mierune.co.jp/posts/a"
            )
