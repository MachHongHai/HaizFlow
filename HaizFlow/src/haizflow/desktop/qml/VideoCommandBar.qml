import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal requestReviewTranslation()

    readonly property bool hasOutput: AppController.hasSelectedOutput
    readonly property bool hasProject: AppController.hasOpenProject
    readonly property bool selectedProcessing: AppController.isSelectedVideoProcessing
    readonly property bool canStart: AppController.hasSelectedVideo && AppController.selectedStatus === "pending"
        && !AppController.isSelectedVideoQueued
    readonly property bool canRestart: AppController.hasSelectedVideo && !AppController.isSelectedVideoProcessing
        && !AppController.isSelectedVideoQueued
        && AppController.selectedStatus !== "pending"
    readonly property string headline: root.selectedProcessing
        ? I18n.t(AppController.selectedStageLabel)
        : AppController.selectedProgress >= 100
            ? I18n.t("Last export ready")
            : AppController.hasSelectedVideo
                ? I18n.t(AppController.selectedStageLabel)
                : I18n.t("Ready to process")

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
                : root.selectedProcessing ? Theme.warningMuted
                : Theme.surfaceElevated

            AppIcon {
                anchors.centerIn: parent
                width: 20
                height: 20
                glyph: AppController.selectedStatus === "done" ? "\uE73E"
                    : AppController.selectedStatus === "failed" ? "\uEA39"
                    : root.selectedProcessing ? "\uE895"
                    : "\uE946"
                iconColor: AppController.selectedStatus === "done" ? Theme.success
                    : AppController.selectedStatus === "failed" ? Theme.danger
                    : root.selectedProcessing ? Theme.warning
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
                        ? I18n.t("Time running")
                        : I18n.t("Processing time")) + " " + AppController.selectedElapsed
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
                visible: AppController.selectedStatus === "paused"
                text: I18n.t("Resume")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: AppController.resumeSelectedVideo()
            }

            AppButton {
                visible: AppController.selectedStatus === "awaiting_review"
                text: I18n.t("Review translation")
                iconGlyph: "\uE70F"
                tone: "primary"
                onClicked: root.requestReviewTranslation()
            }

            AppButton {
                visible: root.canStart
                text: I18n.t("Process")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: AppController.startProjectVideo()
            }

            AppButton {
                visible: root.canRestart
                text: I18n.t("Restart")
                iconGlyph: "\uE72C"
                tone: "primary"
                onClicked: AppController.restartSelectedVideo()
            }

            AppButton {
                visible: root.selectedProcessing
                text: I18n.t("Pause")
                iconGlyph: "\uE769"
                tone: "danger"
                onClicked: AppController.stopVideo()
            }

            AppButton {
                visible: AppController.hasSelectedVideo
                text: I18n.t("Open output video")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: root.hasOutput
                onClicked: AppController.openOutputFile()
            }

            IconButton {
                id: moreButton
                visible: AppController.isSelectedBatchVideo

                property bool menuWasOpenOnPress: false

                glyph: "\uE712"
                // Keep the screen-reader label without showing a tooltip over
                // the menu trigger after it has been clicked.
                Accessible.name: I18n.t("More actions")
                onPressed: menuWasOpenOnPress = videoMenu.visible
                onClicked: {
                    if (menuWasOpenOnPress || videoMenu.visible)
                        videoMenu.close()
                    else
                        videoMenu.open()
                }

                Menu {
                    id: videoMenu
                    width: 242
                    y: -height - 8
                    padding: 6
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

                    enter: Transition {
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionFast }
                    }
                    exit: Transition {
                        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
                    }

                    background: Rectangle {
                        color: Theme.surfaceElevated
                        radius: Theme.radius
                        border.width: 1
                        border.color: Theme.outlineStrong
                    }

                    AppMenuItem {
                        text: I18n.t("Open input video")
                        iconGlyph: "\uE714"
                        collapsed: !AppController.isSelectedBatchVideo
                        onTriggered: AppController.openInputFile()
                    }

                    AppMenuItem {
                        text: I18n.t("Open export folder")
                        iconGlyph: "\uE8B7"
                        collapsed: !AppController.isSelectedBatchVideo
                        onTriggered: AppController.openOutputFolder()
                    }

                    AppMenuItem {
                        text: I18n.t("Remove video")
                        iconGlyph: "\uE74D"
                        tone: "danger"
                        collapsed: !AppController.isSelectedBatchVideo
                        onTriggered: AppController.deleteSelectedVideo()
                    }

                }
            }
        }
    }
}
