import configparser
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.package import build


class PackageTests(unittest.TestCase):
    def test_installable_layout_and_release_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build(Path(directory) / "plugin.zip", "v1.2.3")
            with ZipFile(path) as archive:
                names = archive.namelist()
                self.assertIn("qgislab_plugin/qgislab/logo.svg", names)
                self.assertIn("qgislab_plugin/__init__.py", names)
                self.assertIn("qgislab_plugin/qgislab/plugin.py", names)
                self.assertIn("qgislab_plugin/qgislab/reader.py", names)
                self.assertIn("qgislab_plugin/qgislab/content.py", names)
                self.assertNotIn("qgislab_plugin/qgislab/browser.py", names)
                self.assertFalse(
                    any("tests/" in name or "__pycache__" in name for name in names)
                )
                metadata = configparser.ConfigParser()
                metadata.read_string(
                    archive.read("qgislab_plugin/metadata.txt").decode()
                )
                self.assertEqual(metadata["general"]["version"], "1.2.3")
                self.assertIn("qgislab_plugin/" + metadata["general"]["icon"], names)
