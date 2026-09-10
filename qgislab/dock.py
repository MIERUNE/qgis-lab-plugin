"""A native article library beside a portable QGIS LAB article reader."""

from pathlib import Path

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QRect, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QFont, QIcon, QPalette
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .articles import SITE_URL, Article, article_url, clean_title
from .reader import ArticleReader
from .search import PAGE_SIZE, SearchClient, SearchResult
from .storage import Library
from .thumbnails import ArticleList


class ArticleDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.saved_icon = QIcon(
            str(Path(__file__).parent / "icons" / "star-filled.svg")
        )

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )
        article, saved = index.data(Qt.ItemDataRole.UserRole)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        color = opt.palette.color(
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        )
        painter.save()
        painter.setClipRect(opt.rect)
        painter.setPen(color)
        box = opt.rect.adjusted(14, 10, -14, -10)
        if article.thumbnail:
            frame = QRect(box.x(), box.y(), 96, 54)
            painter.fillRect(frame, opt.palette.color(QPalette.ColorRole.AlternateBase))
            image = self.parent().thumbnail(article.thumbnail)
            if image is not None:
                size = image.size().scaled(
                    frame.size(), Qt.AspectRatioMode.KeepAspectRatio
                )
                target = QRect(0, 0, size.width(), size.height())
                target.moveCenter(frame.center())
                painter.drawImage(target, image)
            box.adjust(108, 0, 0, 0)
        font = QFont(opt.font)
        font.setBold(True)
        painter.setFont(font)
        line = painter.fontMetrics().height()
        title_box = QRect(box.x(), box.y(), box.width(), line * 2)
        painter.drawText(
            title_box,
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop,
            article.title,
        )
        painter.setFont(opt.font)
        metrics = painter.fontMetrics()
        meta = " · ".join(
            filter(None, (article.published, " / ".join(article.categories)))
        )
        icon_size = metrics.height()
        meta_width = max(0, box.width() - (icon_size + 5 if saved else 0))
        meta = metrics.elidedText(meta, Qt.TextElideMode.ElideRight, meta_width)
        meta_y = box.y() + line * 2 + 5
        painter.drawText(
            QRect(box.x(), meta_y, meta_width, metrics.height()),
            Qt.AlignmentFlag.AlignLeft,
            meta,
        )
        if saved:
            self.saved_icon.paint(
                painter,
                QRect(
                    box.x() + metrics.horizontalAdvance(meta) + 5,
                    meta_y,
                    icon_size,
                    icon_size,
                ),
            )
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(240, max(54, option.fontMetrics.height() * 3 + 5) + 20)


class LabDock(QDockWidget):
    def __init__(self, iface, settings=None):
        super().__init__("QGIS LAB", iface.mainWindow())
        self.setObjectName("QgisLabDock")
        font = QFont(self.font())
        font.setPointSize(11)
        self.setFont(font)
        self.setStyleSheet(
            "QDockWidget#QgisLabDock QLineEdit { padding: 7px; border-radius: 5px; }"
            "QDockWidget#QgisLabDock QPushButton { padding: 5px 9px; }"
            "QDockWidget#QgisLabDock QListWidget { border: 1px solid palette(mid); border-radius: 6px; }"
        )
        self.settings = settings if settings is not None else QgsSettings()
        self.library = Library(self.settings)
        self.started = False
        self.results = SearchResult([], 0, 0, PAGE_SIZE)
        self.search_page = 1
        self.search_pending = False
        self.opened_article = None
        self.setMinimumSize(640, 400)
        root = QWidget(self)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 10)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = self.sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 8, 8, 0)
        self.tabs = QTabBar()
        self.tabs.addTab("記事一覧")
        self.tabs.addTab(
            QIcon(str(Path(__file__).parent / "icons" / "star-filled.svg")), "保存済み"
        )
        self.tabs.setExpanding(True)
        side.addWidget(self.tabs)
        self.search = QLineEdit()
        self.search.setPlaceholderText("サイト全体の記事を検索…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("サイト全体の記事を検索")
        self.search_controls = QWidget()
        search_row = QHBoxLayout(self.search_controls)
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search_retry = QPushButton()
        self.search_retry.setIcon(
            QIcon(str(Path(__file__).parent / "icons" / "refresh.svg"))
        )
        self.search_retry.setToolTip("再検索")
        self.search_retry.setAccessibleName("再検索")
        search_row.addWidget(self.search_retry)
        search_row.addWidget(self.search, 1)
        side.addWidget(self.search_controls)
        row = QHBoxLayout()
        self.count = QLabel()
        row.addWidget(self.count)
        row.addStretch()
        side.addLayout(row)
        self.list = ArticleList()
        self.list.setItemDelegate(ArticleDelegate(self.list))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setAccessibleName("QGIS LAB 記事一覧")
        self.list.setSpacing(3)
        side.addWidget(self.list, 1)
        self.pagination = QWidget()
        pages = QHBoxLayout(self.pagination)
        pages.setContentsMargins(0, 0, 0, 0)
        self.previous_page = QPushButton("前のページ")
        self.next_page = QPushButton("次のページ")
        pages.addWidget(self.previous_page)
        pages.addWidget(self.next_page)
        side.addWidget(self.pagination)
        self.search_status = QLabel()
        self.search_status.setWordWrap(True)
        side.addWidget(self.search_status)
        self.empty = QLabel()
        self.empty.setWordWrap(True)
        side.addWidget(self.empty)
        sidebar.setMinimumWidth(260)
        self.splitter.addWidget(sidebar)
        reader = QWidget()
        read = QVBoxLayout(reader)
        read.setContentsMargins(8, 8, 0, 0)
        nav = QHBoxLayout()
        self.reload_button = QPushButton()
        self.reload_button.setIcon(
            QIcon(str(Path(__file__).parent / "icons" / "refresh.svg"))
        )
        self.reload_button.setToolTip("再読込")
        self.reload_button.setAccessibleName("再読込")
        home = QPushButton()
        home.setIcon(QIcon(str(Path(__file__).parent / "icons" / "home.svg")))
        home.setToolTip("ホーム")
        home.setAccessibleName("ホーム")
        for button in (self.reload_button, home):
            nav.addWidget(button)
        nav.addStretch()
        self.save_button = QPushButton()
        bookmark_icon = QIcon(str(Path(__file__).parent / "icons" / "star.svg"))
        bookmark_icon.addFile(
            str(Path(__file__).parent / "icons" / "star-filled.svg"),
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.On,
        )
        self.save_button.setIcon(bookmark_icon)
        self.save_button.setIconSize(QSize(20, 20))
        self.save_button.setObjectName("bookmark")
        self.save_button.setCheckable(True)
        nav.addWidget(self.save_button)
        external = self.external_button = QPushButton("↗ ブラウザで開く")
        nav.addWidget(external)
        read.addLayout(nav)
        self.reader = ArticleReader(reader)
        read.addWidget(self.reader, 1)
        self.splitter.addWidget(reader)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([320, 720])
        saved_state = self.settings.value("qgislab/splitter")
        if saved_state is not None:
            self.splitter.restoreState(saved_state)
        outer.addWidget(self.splitter, 1)
        self.setWidget(root)
        self.search_client = SearchClient(self)
        self.search_client.loaded.connect(self._search_loaded)
        self.search_client.failed.connect(self._search_failed)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self._run_search)
        self.tabs.currentChanged.connect(self.render_list)
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._run_search)
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.search_retry.clicked.connect(self._run_search)
        self.list.currentItemChanged.connect(self._selected)
        self.save_button.clicked.connect(self._toggle_bookmark)
        self.reader.changed.connect(self._page_changed)
        self.reload_button.clicked.connect(self.reader.reload)
        home.clicked.connect(lambda: self.reader.open(SITE_URL))
        external.clicked.connect(self.reader.open_external)
        self.render_list()
        self._page_changed()

    def start(self):
        if not self.started:
            self.started = True
            self.reader.open(SITE_URL)
            self._run_search()

    def render_list(self, *_):
        selected = self.list.currentItem()
        selected_url = (
            selected.data(Qt.ItemDataRole.UserRole)[0].url if selected else ""
        )
        source = (
            self.library.bookmarks
            if self.tabs.currentIndex() == 1
            else self.results.articles
        )
        saved_tab = self.tabs.currentIndex() == 1
        articles = source
        self.list.blockSignals(True)
        self.list.clear()
        for article in articles:
            item = QListWidgetItem(article.title)
            item.setData(
                Qt.ItemDataRole.UserRole, (article, self.library.is_saved(article.url))
            )
            item.setToolTip(article.title + "\n" + article.url)
            self.list.addItem(item)
            if article.url == selected_url:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.count.setVisible(not saved_tab)
        self.count.setText(
            ""
            if saved_tab
            else "検索中…"
            if self.search_pending
            else f"{self.results.offset + 1}–{self.results.offset + len(articles)} / {self.results.total} 件"
            if articles
            else f"0 / {self.results.total} 件"
        )
        self.pagination.setVisible(not saved_tab)
        self.search_status.setVisible(not saved_tab)
        self.previous_page.setEnabled(not self.search_pending and self.search_page > 1)
        self.next_page.setEnabled(
            not self.search_pending
            and self.results.offset + self.results.limit < self.results.total
        )
        self.search_controls.setVisible(not saved_tab)
        self.search_retry.setEnabled(not self.search_pending)
        self.tabs.setTabText(1, f"保存済み ({len(self.library.bookmarks)})")
        self.empty.setVisible(not articles and (saved_tab or not self.search_pending))
        self.empty.setText(
            "検索に一致する記事がありません。"
            if not saved_tab and self.search.text().strip()
            else "まだ保存した記事はありません。記事を開いて星ボタンを押すと保存できます。"
            if self.tabs.currentIndex() == 1
            else "記事がありません。検索欄の左の更新ボタンで再試行できます。"
        )

    def _search_changed(self, *_):
        self.search_timer.stop()
        self.search_client.cancel()
        self.search_page = 1
        self.results = SearchResult([], 0, 0, PAGE_SIZE)
        self.search_pending = True
        self.search_status.clear()
        self.render_list()
        self.search_timer.start()

    def _run_search(self):
        self.search_timer.stop()
        self.search_pending = True
        self.search_status.setText("記事を検索中…")
        self.render_list()
        self.search_client.search(self.search.text(), self.search_page)

    def _change_page(self, delta):
        self.search_page += delta
        self._run_search()

    def _search_loaded(self, result):
        self.search_pending = False
        self.results = result
        self.search_page = result.offset // result.limit + 1
        self.search_status.clear()
        self.render_list()

    def _search_failed(self, message):
        self.search_pending = False
        self.search_page = self.results.offset // self.results.limit + 1
        self.search_status.setText(
            message + "\n検索欄の左の更新ボタンで再試行できます。"
        )
        self.render_list()

    def _selected(self, current, previous):
        if current:
            article = current.data(Qt.ItemDataRole.UserRole)[0]
            self.opened_article = article
            self.reader.open(article.url)

    def _current_article(self):
        url = article_url(self.reader.current_url)
        if not url:
            return None
        return (
            (
                self.opened_article
                if self.opened_article and self.opened_article.url == url
                else None
            )
            or self.library.find(url)
            or next((a for a in self.results.articles if a.url == url), None)
            or Article(
                url, clean_title(self.reader.current_title) or url.rsplit("/", 1)[-1]
            )
        )

    def _page_changed(self):
        article = self._current_article()
        self.save_button.setEnabled(article is not None)
        saved = bool(article and self.library.is_saved(article.url))
        self.save_button.setChecked(saved)
        label = "ブックマークを解除" if saved else "ブックマークに保存"
        self.save_button.setToolTip(label)
        self.save_button.setAccessibleName(label)
        button_height = max(
            32,
            self.save_button.sizeHint().height(),
            self.external_button.sizeHint().height(),
        )
        self.save_button.setFixedSize(button_height, button_height)
        self.external_button.setFixedHeight(button_height)
        self.reload_button.setEnabled(bool(article))

    def _toggle_bookmark(self):
        article = self._current_article()
        if article:
            self.library.toggle(article)
            self.render_list()
            self._page_changed()

    def closeEvent(self, event):
        self.settings.setValue("qgislab/splitter", self.splitter.saveState())
        super().closeEvent(event)

    def shutdown(self):
        self.settings.setValue("qgislab/splitter", self.splitter.saveState())
        self.search_timer.stop()
        self.search_client.cancel()
        self.list.shutdown()
        self.reader.shutdown()
