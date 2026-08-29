pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
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
        qsTr("Dịch"),
        qsTr("Hình ảnh"),
        qsTr("Giọng đọc"),
        qsTr("Âm thanh")
    ]

    implicitHeight: 44
    color: Theme.surface
    border.width: 1
    border.color: Theme.divider
    radius: Theme.radiusSmall

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space4
        spacing: Theme.space4

        Repeater {
            model: root.stageIds.length

            delegate: Rectangle {
                id: stageButton
                required property int index

                readonly property string stageId: root.stageIds[index]
                readonly property bool selected: root.selectedStage === index
                readonly property bool running: root.runningStage === stageId
                    || (stageId === "audio" && root.runningStage === "timeline")
                readonly property bool completed: root.completedStages.indexOf(stageId) >= 0

                Layout.fillWidth: true
                Layout.preferredHeight: 34
                radius: Theme.radiusTiny
                color: selected ? Theme.sidebarSelected
                    : stageHover.hovered ? Theme.surfaceMuted : "transparent"
                border.width: activeFocus ? 2 : 0
                border.color: Theme.focus
                enabled: root.hasVideo
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: root.stageLabels[index]

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space8
                    anchors.rightMargin: Theme.space8
                    spacing: Theme.space8

                    Rectangle {
                        Layout.preferredWidth: 3
                        Layout.preferredHeight: 16
                        radius: 1
                        color: stageButton.running ? Theme.warning
                            : stageButton.selected ? Theme.interactive
                            : stageButton.completed ? Theme.success : "transparent"
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.stageLabels[stageButton.index]
                        color: stageButton.enabled ? Theme.text : Theme.textDisabled
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: stageButton.selected ? Font.DemiBold : Font.Normal
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

        StudioButton {
            Layout.preferredWidth: 124
            text: root.processing && root.runningStage === "render"
                ? qsTr("Tạm dừng") : qsTr("Xuất video")
            iconName: root.processing && root.runningStage === "render" ? "pause" : "publish"
            variant: root.processing && root.runningStage === "render" ? "danger" : "primary"
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
