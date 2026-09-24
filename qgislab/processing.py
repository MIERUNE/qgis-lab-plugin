"""Article search as a Processing table, usable from the toolbox and models."""

from qgis.core import (
    Qgis,
    QgsBlockingNetworkRequest,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingProvider,
)
from qgis.PyQt.QtCore import QMetaType, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .search import PAGE_SIZE, parse_results, search_url


class LabProvider(QgsProcessingProvider):
    def id(self):
        return "qgislab"

    def name(self):
        return "QGIS LAB"

    def loadAlgorithms(self):
        self.addAlgorithm(SearchArticles())


class SearchArticles(QgsProcessingAlgorithm):
    def name(self):
        return "searcharticles"

    def displayName(self):
        return "記事を検索"

    def shortHelpString(self):
        return (
            "QGIS LABの記事をキーワードで検索し、新しい順に属性テーブルへ出力します。"
            "インターネット接続が必要です。キーワードが空の場合は最新記事を取得します。\n"
            "取得上限は既定で100件です。出力列はtitle（タイトル）、url（記事URL）、"
            "summary（概要）、published（公開日）、categories（カテゴリ）です。"
        )

    def createInstance(self):
        return SearchArticles()

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString("QUERY", "検索キーワード", optional=True)
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "MAX_RESULTS",
                "取得上限",
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=100,
                minValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT", "検索結果", type=Qgis.ProcessingSourceType.Vector
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        query = self.parameterAsString(parameters, "QUERY", context)
        maximum = self.parameterAsInt(parameters, "MAX_RESULTS", context)
        fields = QgsFields()
        for name in ("title", "url", "summary", "published", "categories"):
            fields.append(QgsField(name, QMetaType.Type.QString))
        sink, destination = self.parameterAsSink(
            parameters, "OUTPUT", context, fields, Qgis.WkbType.NoGeometry
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, "OUTPUT"))

        count, page = 0, 1
        try:
            while count < maximum and not feedback.isCanceled():
                feedback.setProgressText(f"記事を検索中（{page}ページ目）")
                request = QNetworkRequest(QUrl(search_url(query, page)))
                request.setAttribute(
                    QNetworkRequest.Attribute.RedirectPolicyAttribute,
                    QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
                )
                # QGIS handles proxy settings, timeouts and in-flight cancellation.
                network = QgsBlockingNetworkRequest()
                error = network.get(request, feedback=feedback)
                if feedback.isCanceled():
                    break
                if error != QgsBlockingNetworkRequest.ErrorCode.NoError:
                    raise QgsProcessingException(
                        "記事検索に失敗しました: " + network.errorMessage()
                    )
                try:
                    result = parse_results(bytes(network.reply().content()))
                except ValueError as error:
                    raise QgsProcessingException(str(error)) from error
                # A changed paging contract must not silently repeat the first page.
                if result.offset != (page - 1) * PAGE_SIZE or result.limit != PAGE_SIZE:
                    raise QgsProcessingException(
                        "記事検索のページ情報が正しくありません。"
                    )
                for article in result.articles:
                    if count >= maximum or feedback.isCanceled():
                        break
                    feature = QgsFeature(fields)
                    feature.setAttributes(
                        [
                            article.title,
                            article.url,
                            article.summary,
                            article.published,
                            ", ".join(article.categories),
                        ]
                    )
                    if not sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert):
                        raise QgsProcessingException("検索結果を書き込めませんでした。")
                    count += 1
                feedback.setProgress(100 * count / max(1, min(maximum, result.total)))
                if not result.articles or result.offset + result.limit >= result.total:
                    break
                page += 1
        finally:
            sink.finalize()
        if not feedback.isCanceled():
            feedback.setProgress(100)
        feedback.pushInfo(f"{count}件の記事を出力しました。")
        return {"OUTPUT": destination}
