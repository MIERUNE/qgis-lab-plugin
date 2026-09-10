"""Bounded asynchronous downloads through QGIS's network manager."""

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QObject, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest


class HttpGet(QObject):
    loaded = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, url, byte_limit, parent=None):
        super().__init__(parent)
        self.url = url
        self.byte_limit = byte_limit
        self.reply = None
        self.buffer = bytearray()
        self.failure = ""
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._abort("取得がタイムアウトしました。"))

    def start(self):
        if self.reply is not None:
            return
        self.buffer.clear()
        self.failure = ""
        request = QNetworkRequest(QUrl(self.url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        self.reply = QgsNetworkAccessManager.instance().get(request)
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finished)
        self.timer.start(30000)

    def _read(self):
        if self.reply is None or self.failure:
            return
        self.buffer.extend(bytes(self.reply.readAll()))
        if len(self.buffer) > self.byte_limit:
            self._abort("取得サイズが上限を超えています。")

    def _abort(self, message):
        if self.reply is not None:
            self.failure = message
            self.reply.abort()

    def _finished(self):
        reply, self.reply = self.reply, None
        self.timer.stop()
        self.buffer.extend(bytes(reply.readAll()))
        failure = self.failure
        if len(self.buffer) > self.byte_limit:
            failure = "取得サイズが上限を超えています。"
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if not failure and (
            reply.error() != QNetworkReply.NetworkError.NoError or status != 200
        ):
            failure = (
                f"取得できませんでした（HTTP {status or '—'}）: {reply.errorString()}"
            )
        reply.deleteLater()
        data = bytes(self.buffer)
        self.buffer.clear()
        if failure:
            self.failed.emit(failure)
        else:
            self.loaded.emit(data)

    def cancel(self):
        self.timer.stop()
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.readyRead.disconnect(self._read)
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
        self.buffer.clear()
