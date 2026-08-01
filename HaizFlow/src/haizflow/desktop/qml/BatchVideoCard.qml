import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string videoSize

    signal activated()

    readonly property string statusLabel: status === "pending" ? I18n.t("Queued")
        : status === "processing" ? I18n.t("Processing")
        : status === "done" ? I18n.t("Complete")
        : status === "failed" ? I18n.t("Failed")
        : status === "cancelled" ? I18n.t("Cancelled")
        : status === "paused" ? I18n.t("Paused")
        : status === "awaiting_review" ? I18n.t("Review needed")
        : I18n.taskStateLabel(status)
    readonly property color statusColor: status === "done" ? Theme.success
        : status === "failed" || status === "cancelled" ? Theme.danger
        : status === "processing" ? Theme.warning
        : Theme.textMuted
    readonly property color baseColor: status === "processing" ? Theme.warmSurface
        : status === "awaiting_review" ? Theme.violetSurface
        : status === "failed" || status === "cancelled" ? Theme.dangerMuted
        : Theme.surface
    readonly property color stateOutline: status === "processing" ? Theme.amberMuted
        : status === "awaiting_review" ? Theme.violetOutline
        : status === "failed" || status === "cancelled" ? Theme.danger
        : Theme.outline

    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : root.baseColor
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus
        : hoverHandler.hovered ? Theme.outlineStrong : root.stateOutline
    focusPolicy: Qt.TabFocus
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1, %2").arg(fileName).arg(I18n.t("Edit video settings"))
    scale: tapHandler.pressed ? 0.99 : 1

    function resetFocusState() {
        root.focus = false
    }

    GridView.onPooled: {
        root.visible = false
        root.resetFocusState()
    }
    GridView.onReused: {
        root.visible = true
        root.resetFocusState()
    }

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tapHandler
        onTapped: {
            root.activated()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(root.width * 0.56)
            radius: Theme.radius
            color: Theme.video
            clip: true

            Image {
                id: thumbnailImage
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: Math.round(root.width * 2)
                sourceSize.height: Math.round(root.width * 1.12)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            AppIcon {
                anchors.centerIn: parent
                visible: root.thumbnailSource.length === 0 || thumbnailImage.status === Image.Error
                width: 28
                height: 28
                glyph: "\uE714"
                iconColor: Theme.textSubtle
                iconSize: Theme.iconLarge
            }

            Row {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                spacing: Theme.space4

                Rectangle {
                    width: sizeLabel.implicitWidth + Theme.space12
                    height: 26
                    radius: Theme.radiusSmall
                    color: Theme.scrim

                    Text {
                        id: sizeLabel
                        anchors.centerIn: parent
                        text: I18n.t(root.videoSize)
                        color: Theme.textOnDark
                        font.pixelSize: Theme.label
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }

            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 11
            Layout.bottomMargin: 11
            spacing: 7

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: 4
                    color: root.statusColor
                }

                Text {
                    Layout.fillWidth: true
                    text: root.statusLabel
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    text: qsTr("%1%").arg(root.progress)
                    color: root.statusColor
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppIcon {
                    Layout.preferredWidth: 16
                    Layout.preferredHeight: 16
                    glyph: "\uE70F"
                    iconColor: hoverHandler.hovered ? Theme.violet : Theme.textSubtle
                    iconSize: Theme.iconSmall
                    Accessible.ignored: true
                }
            }
        }
    }

    transform: Translate {
        y: hoverHandler.hovered ? -2 : 0
        Behavior on y {
            NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
        }
    }
    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on border.color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on scale {
        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
    }
}
