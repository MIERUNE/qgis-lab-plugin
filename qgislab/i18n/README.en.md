# Translation Guide

*日本語: [README.md](README.md)*

This plugin does not use Qt's .ts/.qm pipeline. Instead it translates via a
**JSON dictionary keyed by the English source string**. `i18n/__init__.py`
loads the dictionary and performs lookups.

## Files

```
i18n/
├── __init__.py   # load(locale) and tr(message)
├── extract.py    # extract tr("...") from the code and update the JSON (pylupdate equivalent)
├── ja.json       # Japanese translations (source -> translation)
└── en.json       # (optional) English. The source is English, so this is unnecessary
```

## How it works

1. **Translation function**: code calls `i18n.tr("English source")`. `tr()` looks
   up the dictionary and returns the source string when the key is missing or its
   translation is empty (i.e. English fallback).
2. **Locale detection**: on plugin init, `i18n.load(QgsApplication.instance().locale())`
   is called once to load `<locale>.json`. A QGIS locale change takes effect after a
   QGIS restart (same behavior as the Qt approach).
3. Placeholders go in the source string; apply `.format()` at the call site:
   `i18n.tr("count: {}").format(n)`

## Usage

### Translating in code

Import the `i18n` module and call `i18n.tr(...)` (the same inside QObject
subclasses). Calling through the module — rather than `from ..i18n import tr` —
makes the origin explicit and easier to read.

```python
from . import i18n  # adjust the relative path to the file location (.. / ... etc.)

label.setText(i18n.tr("Save Map"))
msg = i18n.tr("An error occurred: {}").format(error_text)
```

### Adding / updating translation keys

After writing a new `tr("...")`, run the extraction script. Keys present in the
code but missing from the JSON are added with an empty translation `""`; keys
present in the JSON but absent from the code are reported as "unused" (never
deleted automatically):

```bash
python3 qgislab/i18n/extract.py            # update qgislab/i18n/ja.json
python3 qgislab/i18n/extract.py --check    # exit non-zero if out of date (for CI)
```

Then fill in the empty translations in `qgislab/i18n/ja.json` (edit directly; no binary
compilation step).

## Article language

The language of the **articles** follows the same QGIS locale but is decided
separately (`articles.site_language()`): a `ja` locale shows the Japanese site as
before, every other locale shows the English articles only (`/en/posts/<id>`, and
`/_api/posts?locale=en`, which lists only articles that have an English version).
The reader never opens an article of the other language, and bookmarks of both
languages are kept but only the current language's are listed.

## Supported languages

- English (en) — default (the source)
- Japanese (ja) — `ja.json`
