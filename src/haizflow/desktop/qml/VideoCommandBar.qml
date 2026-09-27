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
    readonly property string headline: AppController.selectedStatus === "failed"
        ? qsTr("Xử lý thất bại")
        : AppController.selectedStatus === "cancelled"
            ? qsTr("Đã dừng")
            : AppController.selectedStatus === "done" && root.hasOutput
                ? qsTr("Video xuất đã sẵn sàng")
                : AppController.selectedStatus === "awaiting_review"
                    ? qsTr("Cần duyệt phụ đề")
                    : AppController.hasSelectedVideo
                        ? AppController.selectedStageLabel
                        : qsTr("Sẵn sàng xử lý")

    implicitHeight: 44
    color: "transparent"
    border.width: 0

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space4
        anchors.rightMargin: Theme.space4
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: root.headline
            color: AppController.selectedStatus === "failed" ? Theme.danger : Theme.text
            font.pixelSize: Theme.body
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        Text {
            visible: AppController.selectedElapsed.length > 0
            text: qsTr("Thời gian: %1").arg(AppController.selectedElapsed)
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
        }

        RowLayout {
            spacing: Theme.space8

            StudioButton {
                visible: root.canReview
                text: qsTr("Duyệt phụ đề")
                iconGlyph: "\uE70F"
                variant: "primary"
                onClicked: root.requestReviewTranslation()
            }

            StudioButton {
                visible: AppController.selectedStatus === "paused" && !root.selectedQueued
                text: qsTr("Tiếp tục")
                iconGlyph: "\uE768"
                variant: "primary"
                onClicked: AppController.resumeSelectedVideo()
            }

            StudioButton {
                visible: root.canStart
                text: qsTr("Xử lý")
                iconGlyph: "\uE768"
                variant: "primary"
                onClicked: AppController.startProjectVideo()
            }

            StudioButton {
                visible: root.canRestart
                text: qsTr("Chạy lại")
                iconGlyph: "\uE72C"
                variant: AppController.selectedStatus === "done" ? "secondary" : "primary"
                onClicked: AppController.restartSelectedVideo()
            }

            StudioButton {
                visible: root.selectedProcessing && !root.pausePending
                text: qsTr("Tạm dừng")
                iconGlyph: "\uE769"
                variant: "danger"
                onClicked: AppController.stopVideo()
            }

            StudioButton {
                visible: AppController.hasSelectedVideo
                text: qsTr("Mở video đầu ra")
                iconGlyph: "\uE768"
                variant: "primary"
                enabled: root.hasOutput
                onClicked: AppController.openOutputFile()
            }

        }
    }
}
