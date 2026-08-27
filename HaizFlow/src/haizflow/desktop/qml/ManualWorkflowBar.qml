pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    property int selectedStage: 0
    property var completedStages: []
    property string runningStage: ""
    property bool hasVideo: false
    property bool processing: false
    property bool queued: false
    property bool canExport: false
    signal stageSelected(int index)
    signal exportRequested()
    signal pauseRequested()

    readonly property var stageIds: ["translation", "visual", "voice", "audio"]
    readonly property var stageLabels: [
        I18n.t("Translate"),
        I18n.t("Visuals"),
        I18n.t("Voice"),
        I18n.t("Audio")
    ]

    tone: "violet"
    contentPadding: Theme.space8
    contentSpacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Repeater {
            model: root.stageIds.length

            delegate: Rectangle {
                id: stageButton
                required property int index

                readonly property string stageId: root.stageIds[index]
                readonly property bool selected: root.selectedStage === index
                readonly property bool running: root.runningStage === stageId
                    || (stageId === "audio" && root.runningStage === "timeline")

                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: Theme.radiusSmall
                color: selected || running ? Theme.interactiveMuted
                    : stageHover.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
                border.width: selected ? 2 : 1
                border.color: selected || running ? Theme.focus : Theme.outline
                enabled: root.hasVideo
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: root.stageLabels[index]

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space12
                    spacing: Theme.space8

                    Text {
                        Layout.fillWidth: true
                        text: root.stageLabels[stageButton.index]
                        color: Theme.text
                        font.pixelSize: Theme.caption
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                }

                HoverHandler {
                    id: stageHover
                    cursorShape: stageButton.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    enabled: stageButton.enabled
                    onTapped: root.stageSelected(stageButton.index)
                }
                Keys.onReturnPressed: root.stageSelected(stageButton.index)
                Keys.onSpacePressed: root.stageSelected(stageButton.index)
            }
        }

        AppButton {
            Layout.preferredWidth: 142
            text: root.processing && root.runningStage === "render"
                ? I18n.t("Pause") : I18n.t("Export video")
            iconGlyph: root.processing && root.runningStage === "render" ? "\uE769" : "\uE74E"
            tone: root.processing && root.runningStage === "render" ? "danger" : "primary"
            compact: true
            enabled: root.processing && root.runningStage === "render"
                || (!root.queued && root.canExport)
            onClicked: {
                if (root.processing && root.runningStage === "render")
                    root.pauseRequested()
                else
                    root.exportRequested()
            }
        }
    }
}
