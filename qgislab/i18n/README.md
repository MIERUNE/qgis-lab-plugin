# 翻訳ガイド (Translation Guide)

*English: [README.en.md](README.en.md)*

このプラグインは Qt の .ts/.qm パイプラインを使わず、**原文(英語)をキーにした
JSON 辞書**で翻訳する。`i18n/__init__.py` が辞書のロードとルックアップを担う。

## ファイル構成

```
i18n/
├── __init__.py   # load(locale) と tr(message)
├── extract.py    # コードから tr("...") を抽出して JSON を更新（pylupdate 相当）
├── ja.json       # 日本語訳（原文 -> 訳文）
└── en.json       # （任意）英語。原文=英語なので無ければ原文フォールバック
```

## 仕組み

1. **翻訳関数**: コード側は `i18n.tr("英語原文")` を呼ぶ。`tr()` は辞書を引き、未登録なら
   原文をそのまま返す（＝英語フォールバック）。
2. **言語検出**: プラグイン初期化時に `i18n.load(QgsApplication.instance().locale())` を
   1回呼び、`<locale>.json` を読み込む。QGIS のロケール変更は QGIS 再起動で反映される
   （Qt 方式と同じ挙動）。
3. プレースホルダは原文側に書き、`.format()` は呼び出し側で適用する:
   `i18n.tr("count: {}").format(n)`

## 使い方

### コード中で翻訳する

`i18n` モジュールをインポートし、`i18n.tr(...)` で呼ぶ（QObject サブクラス内でも同じ）。
出所が明示され読みやすいので `from ..i18n import tr` ではなくモジュール経由にする。

```python
from . import i18n  # 相対パスはファイル位置に合わせる（.. / ... 等）

label.setText(i18n.tr("Save Map"))
msg = i18n.tr("An error occurred: {}").format(error_text)
```

### 翻訳キーを追加・更新する

新しい `tr("...")` を書いたら抽出スクリプトを実行する。コードに在って JSON に無い
キーは空訳 `""` で追加され、JSON に在ってコードに無いキーは「未使用」として報告される
（自動削除はしない）:

```bash
python3 qgislab/i18n/extract.py            # qgislab/i18n/ja.json を更新
python3 qgislab/i18n/extract.py --check    # 未更新なら非0終了（CI 用）
```

その後 `qgislab/i18n/ja.json` の空訳を埋める（エディタで直接編集。バイナリ化・コンパイル不要）。

## 記事の言語

**記事**の言語も同じ QGIS のロケールに従うが、UI の翻訳とは別に決まる
（`articles.site_language()`）。`ja` なら従来どおり日本語サイト、それ以外は英語の記事のみ
（`/en/posts/<id>`、検索は `/_api/posts?locale=en`。英語版のある記事だけが返る）。
リーダーは別言語の記事を開かず（ブラウザで開く）、ブックマークは両言語分を保持しつつ
現在の言語のものだけを表示する。

## 対応言語

- 英語 (en) — デフォルト（原文）
- 日本語 (ja) — `ja.json`
