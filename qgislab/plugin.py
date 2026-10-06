"""QGIS lifecycle: one dock per plugin instance."""

from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from . import i18n
from .articles import site_language
from .dock import LabDock


class QgisLabPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.init_translation()

    def init_translation(self):
        """Load translations and pick the article language for the QGIS locale."""
        locale = QgsApplication.instance().locale()
        i18n.load(locale)
        self.language = site_language(locale)

    def initGui(self):
        self.action = QAction(
            QIcon(str(Path(__file__).parent.parent / "icon.svg")),
            "QGIS LAB",
            self.iface.mainWindow(),
        )
        self.action.setToolTip(i18n.tr("Read, search and save QGIS LAB articles"))
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu("QGIS LAB", self.action)
        self.iface.addToolBarIcon(self.action)

    def run(self):
        if self.dock is None:
            self.dock = LabDock(self.iface, self.language)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()
        self.dock.start()

    def unload(self):
        if self.dock is not None:
            self.dock.shutdown()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removePluginWebMenu("QGIS LAB", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
