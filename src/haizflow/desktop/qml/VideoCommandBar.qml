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
    readonly property bool canProcess: AppController.hasSelectedVideo && !root.selectedActive
        && !AppController.videoExportBusy
    readonly property bool canReview: AppController.selectedStatus === "awaiting_review"
    readonly property string headline: AppController.selectedStatus === "failed"
        ? AppController.selectedFailureTitle
        : AppController.selectedStatus === "cancelled"
            ? qsTr("Đã dừng")
            : AppController.selectedStatus === "done" && root.hasOutput
                ? qsTr("Video đã xuất")
                : AppController.selectedStatus === "awaiting_review"
                    ? qsTr("Cần duyệt phụ đề")
                    : root.pausePending
                        ? qsTr("Đang tạm dừng…")
                    : AppController.selectedStatus === "paused"
                        ? qsTr("Đã tạm dừng")
                    : AppController.selectedStatus === "pending" && !root.selectedQueued
                        ? qsTr("Chưa xử lý")
                    : root.selectedQueued && !root.selectedProcessing
                        ? qsTr("Đang chờ xử lý")
                    : AppController.hasSelectedVideo
                        ? AppController.selectedStageLabel
                        : qsTr("Chưa chọn video")

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
                variant: "secondary"
                enabled: !AppController.videoExportBusy
                onClicked: AppController.resumeSelectedVideo()
            }

            StudioButton {
                objectName: "autoProcessButton"
                visible: !root.selectedActive
                text: ["paused", "done", "failed", "cancelled", "awaiting_review"].indexOf(AppController.selectedStatus) >= 0
                    ? qsTr("Xử lý lại") : qsTr("Xử lý")
                iconGlyph: "\uE768"
                variant: "primary"
                enabled: root.canProcess
                onClicked: AppController.requestAutoProcessing()
            }

            StudioButton {
                objectName: "autoPauseButton"
                visible: root.selectedActive
                text: root.pausePending ? qsTr("Đang tạm dừng…") : qsTr("Tạm dừng")
                iconGlyph: "\uE769"
                variant: "danger"
                enabled: !root.pausePending
                onClicked: AppController.stopVideo()
            }
        }
    }
}
