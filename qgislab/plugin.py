"""QGIS lifecycle: one dock per plugin instance."""

from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .dock import LabDock
from .processing import LabProvider


class QgisLabPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.provider = None

    def initProcessing(self):
        if self.provider is None:
            self.provider = LabProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        self.action = QAction(
            QIcon(str(Path(__file__).parent.parent / "icon.svg")),
            "QGIS LAB",
            self.iface.mainWindow(),
        )
        self.action.setToolTip("QGIS LABの記事を読む・探す・保存する")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu("QGIS LAB", self.action)
        self.iface.addToolBarIcon(self.action)

    def run(self):
        if self.dock is None:
            self.dock = LabDock(self.iface)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()
        self.dock.start()

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
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
