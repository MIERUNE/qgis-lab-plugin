"""QGIS plugin entry point; keep imports lazy for plugin discovery."""


def classFactory(iface):
    from .qgislab.plugin import QgisLabPlugin

    return QgisLabPlugin(iface)
