import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal requestReviewTranslation()

    readonly property bool hasOutput: AppController.hasSelectedOutput
    readonly property bool hasProject: AppController.hasOpenProject
    readonly property bool selectedProcessing: AppController.isSelectedVideoProcessing
    readonly property bool selectedQueued: AppController.isSelectedVideoQueued
    readonly property bool selectedActive: root.selectedProcessing || root.selectedQueued
    readonly property bool pausePending: AppController.selectedStatus === "paused" && root.selectedQueued
    readonly property bool canStart: AppController.hasSelectedVideo && AppController.selectedStatus === "pending"
        && !root.selectedQueued
    readonly property bool canRestart: AppController.hasSelectedVideo && !root.selectedActive
        && ["paused", "awaiting_review", "done", "failed", "cancelled"].indexOf(AppController.selectedStatus) >= 0
    readonly property bool canReview: AppController.selectedStatus === "awaiting_review"
    readonly property bool canEditSubtitles: AppController.selectedStatus === "done"
        && AppController.canEditSelectedSubtitles
    readonly property string headline: root.selectedActive
        ? AppController.selectedStageLabel
        : AppController.selectedProgress >= 100
            ? qsTr("Video xuất đã sẵn sàng")
            : AppController.hasSelectedVideo
                ? AppController.selectedStageLabel
                : qsTr("Sẵn sàng xử lý")

    implicitHeight: 116
    radius: Theme.radius
    color: Theme.surface
    border.width: 1
    border.color: Theme.outline

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        spacing: Theme.space20

        Rectangle {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            radius: Theme.radiusSmall
            color: AppController.selectedStatus === "done" ? Theme.successMuted
                : AppController.selectedStatus === "failed" ? Theme.dangerMuted
                : root.selectedActive ? Theme.warningMuted
                : Theme.surfaceElevated

            AppIcon {
                anchors.centerIn: parent
                width: 20
                height: 20
                glyph: AppController.selectedStatus === "done" ? "\uE73E"
                    : AppController.selectedStatus === "failed" ? "\uEA39"
                    : root.selectedActive ? "\uE895"
                    : "\uE946"
                iconColor: AppController.selectedStatus === "done" ? Theme.success
                    : AppController.selectedStatus === "failed" ? Theme.danger
                    : root.selectedActive ? Theme.warning
                    : Theme.textMuted
                iconSize: Theme.icon
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 330
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12

                Text {
                    Layout.fillWidth: true
                    text: root.headline
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    text: qsTr("%1%").arg(AppController.selectedProgress)
                    color: AppController.selectedProgress >= 100 ? Theme.success : Theme.interactive
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    visible: AppController.selectedElapsed.length > 0
                    text: (AppController.selectedStatus === "processing"
                        ? qsTr("Thời gian đã chạy")
                        : qsTr("Thời gian xử lý")) + " " + AppController.selectedElapsed
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            Text {
                Layout.fillWidth: true
                text: I18n.progressDetail(AppController.selectedProgressDetail
                    || AppController.selectedStep
                    || "Processing status will appear here")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: AppController.selectedProgress
            }
        }

        RowLayout {
            spacing: Theme.space8

            AppButton {
                visible: root.canReview || root.canEditSubtitles
                text: root.canReview ? qsTr("Duyệt phụ đề") : qsTr("Sửa lại phụ đề")
                iconGlyph: "\uE70F"
                tone: root.canReview ? "primary" : "secondary"
                onClicked: root.requestReviewTranslation()
            }

            AppButton {
                visible: AppController.selectedStatus === "paused" && !root.selectedQueued
                text: qsTr("Tiếp tục")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: AppController.resumeSelectedVideo()
            }

            AppButton {
                visible: root.canStart
                text: qsTr("Xử lý")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: AppController.startProjectVideo()
            }

            AppButton {
                visible: root.canRestart
                text: qsTr("Chạy lại")
                iconGlyph: "\uE72C"
                tone: AppController.selectedStatus === "done" ? "secondary" : "primary"
                onClicked: AppController.restartSelectedVideo()
            }

            AppButton {
                visible: root.selectedProcessing && !root.pausePending
                text: qsTr("Tạm dừng")
                iconGlyph: "\uE769"
                tone: "danger"
                onClicked: AppController.stopVideo()
            }

            AppButton {
                visible: root.selectedQueued && !root.selectedProcessing
                    && AppController.selectedStatus !== "paused"
                text: qsTr("Đang chờ")
                iconGlyph: "\uE895"
                tone: "secondary"
                enabled: false
            }

            AppButton {
                visible: root.pausePending
                text: qsTr("Đang tạm dừng")
                iconGlyph: "\uE895"
                tone: "secondary"
                enabled: false
            }

            AppButton {
                visible: AppController.hasSelectedVideo
                text: qsTr("Mở video đầu ra")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: root.hasOutput
                onClicked: AppController.openOutputFile()
            }

        }
    }
}
