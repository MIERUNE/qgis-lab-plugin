import json
import unittest
from pathlib import Path

from qgislab import i18n
from qgislab.content import extract_content
from qgislab.i18n import extract

JA = Path(i18n.__file__).with_name("ja.json")


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.load("en")

    def test_english_is_the_default_and_fallback(self):
        i18n.load("en")
        self.assertEqual(i18n.tr("Home"), "Home")
        i18n.load("fr_FR")
        self.assertEqual(i18n.tr("Home"), "Home")
        self.assertEqual(i18n.tr("Not a known key"), "Not a known key")

    def test_japanese_by_language_or_full_locale(self):
        for locale in ("ja", "ja_JP"):
            with self.subTest(locale=locale):
                i18n.load(locale)
                self.assertEqual(i18n.tr("Home"), "ホーム")

    def test_empty_translation_falls_back_to_source(self):
        i18n._translations = {"Home": ""}
        self.assertEqual(i18n.tr("Home"), "Home")

    def test_placeholders_are_applied_by_the_caller(self):
        i18n.load("ja")
        self.assertEqual(i18n.tr("Saved ({})").format(3), "保存済み (3)")

    def test_errors_raised_by_core_modules_are_translated(self):
        i18n.load("ja")
        with self.assertRaises(ValueError) as caught:
            extract_content(b"<html></html>", "https://example.com/")
        self.assertEqual(str(caught.exception), "QGIS LABの記事URLではありません。")


class DictionaryTests(unittest.TestCase):
    def test_every_source_string_is_translated_to_japanese(self):
        keys, warnings = extract.collect(extract.ROOT)
        translations = json.loads(JA.read_text(encoding="utf-8"))
        self.assertEqual(warnings, [], "tr() needs a string literal")
        self.assertEqual(sorted(keys - set(translations)), [], "run extract.py")
        self.assertEqual(sorted(k for k in keys if not translations[k]), [])

    def test_translations_keep_the_source_placeholders(self):
        for source, translated in json.loads(JA.read_text(encoding="utf-8")).items():
            with self.subTest(source=source):
                self.assertEqual(source.count("{}"), translated.count("{}"))


if __name__ == "__main__":
    unittest.main()
