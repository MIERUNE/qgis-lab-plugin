"""Visible-row thumbnail loading with bounded requests and a small session cache."""

from collections import OrderedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from qgis.PyQt.QtCore import QBuffer, QIODevice, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QImage, QImageReader
from qgis.PyQt.QtWidgets import QListWidget

from .network import HttpGet


class ArticleList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = OrderedDict()
        self._requests = {}
        self._stopped = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._load_visible)
        self.verticalScrollBar().valueChanged.connect(self._schedule)
        self.model().rowsInserted.connect(self._schedule)
        self.model().rowsRemoved.connect(self._schedule)
        self.model().modelReset.connect(self._schedule)

    def thumbnail(self, url):
        image = self._cache.get(url)
        if url in self._cache:
            self._cache.move_to_end(url)
        return image

    def _schedule(self, *_):
        if not self._stopped:
            self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
        self._cancel_except(set())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule()

    def _cancel_except(self, wanted):
        for url in list(self._requests):
            if url not in wanted:
                request = self._requests.pop(url)
                request.cancel()
                request.deleteLater()

    def _load_visible(self):
        if self._stopped:
            return
        wanted = []
        if self.isVisible():
            viewport = self.viewport().rect()
            for row in range(self.count()):
                item = self.item(row)
                if self.visualItemRect(item).intersects(viewport):
                    article, _ = item.data(Qt.ItemDataRole.UserRole)
                    if article.thumbnail and article.thumbnail not in wanted:
                        wanted.append(article.thumbnail)
        self._cancel_except(set(wanted))
        for url in wanted:
            if len(self._requests) >= 4:
                break
            if url in self._cache or url in self._requests:
                continue
            request = HttpGet(self._download_url(url), 2 * 1024 * 1024, self)
            self._requests[url] = request
            request.loaded.connect(
                lambda data, url=url, request=request: self._loaded(url, request, data)
            )
            request.failed.connect(
                lambda error, url=url, request=request: self._finished(
                    url, request, None
                )
            )
            request.start()

    @staticmethod
    def _download_url(url):
        parts = urlsplit(url)
        if parts.hostname == "images.microcms-assets.io":
            query = dict(parse_qsl(parts.query))
            query.update(w="320", h="180", fit="max", fm="png")
            return urlunsplit(parts._replace(query=urlencode(query)))
        return url

    def _loaded(self, url, request, data):
        if self._requests.get(url) is not request:
            return
        buffer = QBuffer()
        buffer.setData(data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        size = reader.size()
        image = QImage()
        # Only decode bounded raster images, scaled to thumbnail dimensions.
        if (
            bytes(reader.format()).lower() in (b"png", b"jpeg", b"webp", b"gif", b"bmp")
            and 0 < size.width() * size.height() <= 8_000_000
        ):
            reader.setScaledSize(
                size.scaled(QSize(320, 180), Qt.AspectRatioMode.KeepAspectRatio)
            )
            image = reader.read()
        buffer.close()
        self._finished(
            url,
            request,
            None
            if image.isNull()
            else image.scaled(
                QSize(320, 180),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )

    def _finished(self, url, request, image):
        if self._requests.get(url) is not request:
            return
        self._requests.pop(url)
        request.deleteLater()
        # Remember failures too, so scrolling does not repeatedly retry broken URLs.
        self._cache[url] = image
        while len(self._cache) > 64:
            self._cache.popitem(last=False)
        self.viewport().update()
        self._schedule()

    def shutdown(self):
        self._stopped = True
        self._timer.stop()
        self._cancel_except(set())
        self._cache.clear()
