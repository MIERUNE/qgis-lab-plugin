"""Cross-platform article reader using only QGIS and Qt's standard text widget."""

from configparser import ConfigParser
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit

from qgis.PyQt.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from qgis.PyQt.QtGui import (
    QFont,
    QImage,
    QImageReader,
    QPainter,
    QPalette,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from qgis.PyQt.QtWidgets import QTextBrowser

from .articles import SITE_URL, article_url
from .content import MAX_PAGE_BYTES, extract_content, web_url
from .network import HttpGet

IMAGE_TYPE = QTextDocument.ResourceType.ImageResource
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_DECODED_BYTES = 64 * 1024 * 1024


class ArticleReader(QTextBrowser):
    changed = pyqtSignal()
    loading = pyqtSignal(bool)
    failed = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setAccessibleName("QGIS LAB 記事リーダー")
        self.anchorClicked.connect(self._open_link)
        font = QFont(self.font())
        font.setFamilies(["Noto Sans JP", "Hiragino Sans", "Yu Gothic", "sans-serif"])
        font.setPixelSize(16)
        self.setFont(font)
        self.document().setDocumentMargin(24)
        self._logo = QImage(str(Path(__file__).with_name("logo.svg")))
        self.current_url = ""
        self.current_title = ""
        self._history = []
        self._index = -1
        self._generation = 0
        self._request = None
        self._image_requests = {}
        self._queue = []
        self._images = {}
        self._image_errors = 0
        self._decoded_bytes = 0
        self._content = None
        self._restore_position = 0
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._resize_images)
        self.home()

    def _apply_theme(self):
        # Keep all presentation colors here; extracted HTML contains only roles.
        # In particular, never override the palette inherited from QGIS.
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Base).name()
        text = palette.color(QPalette.ColorRole.Text).name()
        dark = palette.color(QPalette.ColorRole.Base).lightness() < 128
        link = "#83cddd" if dark else "#005773"
        muted = "#b6b9b2" if dark else "#777777"
        accent = "#b1cf70" if dark else "#80a728"
        surface = "#343632" if dark else "#f0efef"
        summary = "#2c3423" if dark else "#f2f6e9"
        info = "#34452c" if dark else "#d6ebad"
        caution = "#443b26" if dark else "#fff3cd"
        warning = "#ff9696" if dark else "#ef4444"
        self.document().setDefaultStyleSheet(
            f"body {{ color: {text}; background-color: {base}; }}"
            "p { line-height: 32px; margin-top: 20px; margin-bottom: 20px; }"
            "li { line-height: 24px; margin-top: 0; margin-bottom: 8px; }"
            "ul, ol { margin-top: 16px; margin-bottom: 16px; margin-left: 24px; }"
            "h1 { font-size: 32px; line-height: 54px; margin-top: 8px; margin-bottom: 8px; }"
            "h2 { font-size: 28px; line-height: 36px; margin-top: 32px; margin-bottom: 16px; }"
            "h3 { font-size: 24px; line-height: 32px; margin-top: 32px; margin-bottom: 16px; }"
            "h4 { font-size: 20px; margin-top: 24px; margin-bottom: 12px; }"
            f"a {{ color: {link}; text-decoration: none; }}"
            "p.eyecatch { margin-top: 0; margin-bottom: 32px; line-height: 100%; }"
            "p.category { margin-top: 0; margin-bottom: 8px; line-height: 24px; }"
            f"p.category a {{ color: {text}; }}"
            f"p.dates {{ color: {muted}; margin-top: 4px; margin-bottom: 24px; }}"
            "p.intro { margin-top: 24px; margin-bottom: 24px; }"
            "table.summary, table.callout, table.version { margin-top: 0; margin-bottom: 0; }"
            "table.summary { margin-top: 24px; }"
            "table.callout { margin-top: 20px; }"
            "table.summary td { padding: 12px 20px; }"
            f"h3.summary-title {{ color: {accent}; font-size: 20px; line-height: 28px; margin-top: 0; margin-bottom: 0; }}"
            f"table.summary hr {{ margin-top: 0; margin-bottom: 0; line-height: 1px; color: {accent}; background-color: {accent}; }}"
            "table.summary ul { margin-top: 12px; margin-bottom: 0; margin-left: 0; -qt-list-indent: 1; }"
            "div.figure { margin-top: 24px; margin-bottom: 32px; }"
            f"p.caption {{ color: {muted}; font-size: 14px; line-height: 21px; margin-top: 8px; margin-bottom: 8px; }}"
            f"pre {{ background-color: {surface}; white-space: pre-wrap; margin-top: 20px; margin-bottom: 20px; }}"
            f"code {{ font-family: monospace; background-color: {surface}; }}"
            f"blockquote {{ color: {muted}; margin-left: 20px; }}"
            f"th {{ background-color: {surface}; }}"
            f"table.summary {{ background-color: {summary}; }}"
            f"table.callout {{ background-color: {info}; }}"
            f"table.caution {{ background-color: {caution}; }}"
            f"table.version {{ border: 1px solid {muted}; }}"
            f"span.warning {{ color: {warning}; }}"
            f"span.category-label {{ background-color: {surface}; }}"
            f"table.home-welcome {{ background-color: {summary}; margin-top: 24px; margin-bottom: 16px; }}"
            "table.home-welcome h2 { margin-top: 0; margin-bottom: 12px; font-size: 26px; }"
            "table.home-welcome p { margin-top: 0; margin-bottom: 0; line-height: 28px; }"
            f"td.home-step {{ color: {accent}; font-size: 20px; font-weight: bold; }}"
            "table.home-steps { margin-top: 8px; margin-bottom: 8px; }"
            "table.home-steps p { margin-top: 0; margin-bottom: 0; line-height: 26px; }"
            f"p.home-about {{ color: {muted}; font-size: 14px; line-height: 24px; margin-top: 12px; margin-bottom: 16px; }}"
            "h3.home-about-title { font-size: 18px; margin-top: 24px; margin-bottom: 0; }"
            f"table.home-link {{ background-color: {surface}; margin-bottom: 16px; }}"
            "p.home-version { font-size: 12px; margin-top: 12px; line-height: 20px; }"
        )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ) and hasattr(self, "_html"):
            # Reapply colors without refetching the article.
            position = self.verticalScrollBar().value()
            self.setHtml(self._html)
            self.verticalScrollBar().setValue(position)

    def setHtml(self, html):
        self._html = html
        self._apply_theme()
        super().setHtml(f"<html><body>{html}</body></html>")
        # Qt retains h1–h6's relative size adjustment even with an explicit CSS
        # pixel size. Remove that competing default, preserving links/anchors.
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                if fmt.hasProperty(
                    QTextFormat.Property.FontPixelSize
                ) and fmt.hasProperty(QTextFormat.Property.FontSizeAdjustment):
                    fmt.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(
                        fragment.position() + fragment.length(),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.setCharFormat(fmt)
                iterator += 1
            block = block.next()
        self._resize_images()

    @property
    def can_go_back(self):
        return self._index > 0

    @property
    def can_go_forward(self):
        return self._index + 1 < len(self._history)

    def home(self):
        self.open(SITE_URL)

    def _open_link(self, url):
        # The home action shows our welcome screen; a website link opens the site.
        if url.toString() == SITE_URL:
            self._external(SITE_URL)
        else:
            self.open(url.toString())

    def open(self, url):
        target = web_url(url, self.current_url or SITE_URL)
        if not target:
            return
        canonical = article_url(target)
        if not canonical and target != SITE_URL:
            self._external(target)
            return
        if canonical:
            fragment = urlsplit(target).fragment
            target = canonical + ("#" + fragment if fragment else "")
            if canonical == article_url(self.current_url) and self._content is not None:
                self.current_url = target
                self._restore_position = 0
                self._history[self._index][0] = target
                if fragment:
                    self.scrollToAnchor(unquote(fragment))
                else:
                    self.verticalScrollBar().setValue(0)
                self.changed.emit()
                return
        self._remember_position()
        if self._index < 0 or self._history[self._index][0] != target:
            self._history = self._history[: self._index + 1]
            self._history.append([target, 0])
            # Navigation only stores URLs and positions, not complete pages.
            self._history = self._history[-100:]
            self._index = len(self._history) - 1
        self._navigate(target)

    def _remember_position(self):
        if self._index >= 0:
            self._history[self._index][1] = self.verticalScrollBar().value()

    def back(self):
        if self.can_go_back:
            self._remember_position()
            self._index -= 1
            self._navigate(self._history[self._index][0])

    def forward(self):
        if self.can_go_forward:
            self._remember_position()
            self._index += 1
            self._navigate(self._history[self._index][0])

    def reload(self):
        self._remember_position()
        self._navigate(self.current_url)

    def _navigate(self, url):
        self._cancel_requests()
        self.current_url = url
        self.current_title = ""
        self._content = None
        self._images.clear()
        self._decoded_bytes = 0
        self._image_errors = 0
        self._restore_position = self._history[self._index][1]
        if url == SITE_URL:
            self.current_title = "ホーム"
            self._render_home()
            self.loading.emit(False)
        else:
            self.setHtml("<h2>記事を読み込み中…</h2><p>本文を取得しています。</p>")
            self.loading.emit(True)
            self._request = HttpGet(article_url(url), MAX_PAGE_BYTES, self)
            generation = self._generation
            self._request.loaded.connect(lambda data: self._loaded(data, generation))
            self._request.failed.connect(lambda error: self._failed(error, generation))
            self._request.start()
        self.changed.emit()

    def _render_home(self):
        # Bundle the official logo so home remains usable without a network request.
        self.document().addResource(IMAGE_TYPE, QUrl("qgislab-logo:/"), self._logo)
        # Read the installed metadata so release ZIP versions stay accurate.
        metadata = ConfigParser(interpolation=None)
        metadata.read(
            Path(__file__).resolve().parents[1] / "metadata.txt", encoding="utf-8"
        )
        version = metadata.get("general", "version", fallback="不明")
        self.setHtml(
            '<table cellspacing="0" cellpadding="12" bgcolor="#ffffff"><tr><td>'
            f'<a href="{SITE_URL}"><img src="qgislab-logo:/" width="186" height="54" alt="QGIS LAB by MIERUNE"></a>'
            "</td></tr></table>"
            '<table class="home-welcome" width="100%" cellspacing="0" cellpadding="22"><tr><td>'
            "<h2>記事を選択してください</h2>"
            "<p>左側の「記事一覧」から、読みたい記事を選んでください。</p>"
            "</td></tr></table>"
            '<table class="home-steps" width="100%" cellspacing="0" cellpadding="8">'
            '<tr><td class="home-step" width="56" valign="top">01</td>'
            "<td><p><b>探す</b>　キーワードで記事を検索</p></td></tr>"
            '<tr><td class="home-step" width="56" valign="top">02</td>'
            "<td><p><b>読む</b>　記事を選ぶと、この画面に本文を表示</p></td></tr>"
            '<tr><td class="home-step" width="56" valign="top">03</td>'
            "<td><p><b>保存する</b>　気になる記事をブックマークして、すぐに読む</p></td></tr>"
            "</table>"
            '<h3 class="home-about-title">このプラグインについて</h3>'
            '<p class="home-about">QGIS LABの記事を、QGISで作業しながら読む・探す・保存するためのプラグインです。</p>'
            '<table class="home-link" cellspacing="0" cellpadding="12"><tr><td>'
            f'<a href="{SITE_URL}"><b>QGIS LAB 公式サイトを開く ↗</b></a>'
            "</td></tr></table>"
            f'<p class="dates home-version">QGIS LAB プラグイン · バージョン {escape(version)}</p>'
        )

    def _loaded(self, data, generation):
        if generation != self._generation:
            return
        try:
            self._content = extract_content(data, article_url(self.current_url))
        except ValueError as error:
            self._failed(str(error), generation)
            return
        self._request.deleteLater()
        self._request = None
        self.current_title = self._content.title
        # QTextDocument may retain resource keys across setHtml calls.
        for key in self._content.images:
            self.document().addResource(
                IMAGE_TYPE, QUrl(key), self._placeholder("画像を読み込み中…")
            )
        self.setHtml(self._content.html)
        self.loading.emit(False)
        self.changed.emit()
        self._restore_scroll()
        self._queue = list(self._content.images.items())
        self._start_images()

    def _failed(self, error, generation):
        if generation != self._generation:
            return
        if self._request is not None:
            self._request.deleteLater()
            self._request = None
        self.setHtml(
            "<h2>記事を読み込めませんでした</h2>"
            f"<p>{escape(error)}</p><p>「再読込」で再試行するか、"
            "「ブラウザで開く」から元の記事をご覧ください。</p>"
        )
        self.loading.emit(False)
        self.failed.emit(error)
        self.changed.emit()

    def _start_images(self):
        while self._queue and len(self._image_requests) < 4:
            key, url = self._queue.pop(0)
            request = HttpGet(url, MAX_IMAGE_BYTES, self)
            self._image_requests[key] = request
            generation = self._generation
            request.loaded.connect(
                lambda data, key=key, generation=generation: self._image_loaded(
                    key, data, generation
                )
            )
            request.failed.connect(
                lambda error, key=key, generation=generation: self._image_finished(
                    key, generation, error=True
                )
            )
            request.start()
        pending = len(self._queue) + len(self._image_requests)
        if pending:
            self.message.emit(
                f"本文を表示しました · 画像を読み込み中（残り {pending} 枚）"
            )
        else:
            self.message.emit(
                ""
                if not self._image_errors
                else f"画像 {self._image_errors} 枚を表示できませんでした。元の記事は「ブラウザで開く」から確認できます。"
            )
            self._restore_scroll()

    def _image_loaded(self, key, data, generation):
        if generation != self._generation:
            return
        buffer = QBuffer(self)
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        size = reader.size()
        image = QImage()
        # Bound decoding as well as download size; do not load SVG resources or local files.
        if (
            bytes(reader.format()).lower()
            in (b"png", b"jpeg", b"jpg", b"webp", b"gif", b"bmp")
            and 0 < size.width() * size.height() <= 40_000_000
        ):
            scaled = size.scaled(QSize(1200, 4000), Qt.AspectRatioMode.KeepAspectRatio)
            if size.width() > scaled.width() or size.height() > scaled.height():
                reader.setScaledSize(scaled)
            if (
                self._decoded_bytes
                + min(size.width(), scaled.width())
                * min(size.height(), scaled.height())
                * 4
                <= MAX_DECODED_BYTES
            ):
                image = reader.read()
        buffer.close()
        buffer.deleteLater()
        if (
            not image.isNull()
            and self._decoded_bytes + image.sizeInBytes() <= MAX_DECODED_BYTES
        ):
            self._images[key] = image
            self._decoded_bytes += image.sizeInBytes()
            self.document().addResource(
                IMAGE_TYPE, QUrl(key), self._scaled_image(image)
            )
            self.document().markContentsDirty(0, self.document().characterCount())
            self.viewport().update()
            self._image_finished(key, generation)
        else:
            self._image_finished(key, generation, error=True)

    def _image_finished(self, key, generation, error=False):
        if generation != self._generation:
            return
        request = self._image_requests.pop(key, None)
        if request:
            request.deleteLater()
        if error:
            self._image_errors += 1
            self.document().addResource(
                IMAGE_TYPE, QUrl(key), self._placeholder("画像を表示できませんでした")
            )
            self.document().markContentsDirty(0, self.document().characterCount())
        self._start_images()

    def _scaled_image(self, image):
        frame = self.document().rootFrame().frameFormat()
        width = max(
            1,
            int(self.viewport().width() - frame.leftMargin() - frame.rightMargin() - 4),
        )
        return (
            image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            if image.width() > width
            else image
        )

    def _placeholder(self, text):
        image = QImage(320, 36, QImage.Format.Format_ARGB32)
        image.fill(self.palette().color(QPalette.ColorRole.AlternateBase))
        painter = QPainter(image)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return self._scaled_image(image)

    def loadResource(self, resource_type, name):
        # QTextBrowser's default loader can read local files. All article images must
        # instead be supplied explicitly by our bounded QGIS network requests.
        key = name.toString()
        if resource_type == IMAGE_TYPE and key == "qgislab-logo:/":
            return self._logo
        if resource_type == IMAGE_TYPE and key.startswith("qgislab-image:/"):
            image = self._images.get(key)
            return (
                self._scaled_image(image)
                if image is not None
                else self._placeholder("画像を読み込み中…")
            )
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_resize_timer"):
            self._resize_timer.start(100)

    def _resize_images(self):
        # Match the site's 738px reading column while keeping narrow docks usable.
        # Use the same margins for text layout and image sizing.
        frame = self.document().rootFrame()
        format = frame.frameFormat()
        width = self.viewport().width()
        margin = max(24 if width < 700 else 48, (width - 738) / 2)
        format.setLeftMargin(margin)
        format.setRightMargin(margin)
        frame.setFrameFormat(format)
        for key, image in self._images.items():
            self.document().addResource(
                IMAGE_TYPE, QUrl(key), self._scaled_image(image)
            )
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def _restore_scroll(self):
        fragment = unquote(urlsplit(self.current_url).fragment)
        if self._restore_position:
            self.verticalScrollBar().setValue(self._restore_position)
        elif fragment:
            self.scrollToAnchor(fragment)

    @staticmethod
    def _external(url):
        from qgis.PyQt.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

    def open_external(self):
        if self.current_url:
            self._external(self.current_url)

    def _cancel_requests(self):
        self._generation += 1
        if self._request is not None:
            self._request.cancel()
            self._request.deleteLater()
            self._request = None
        for request in self._image_requests.values():
            request.cancel()
            request.deleteLater()
        self._image_requests.clear()
        self._queue.clear()

    def shutdown(self):
        self._resize_timer.stop()
        self._cancel_requests()
