import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    property string activityState: "ready"
    property string message: ""
    property real progress: -1
    property bool expanded: false
    property bool showDetails: true
    signal detailsRequested()

    // Keep the status strip's geometry stable. Model warm-up used to remove
    // this item when it finished, making every workspace visibly grow after
    // a few seconds even though the window DPI and font sizes had not changed.
    implicitHeight: UiMetrics.activityTrayHeight
    visible: true
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.outline

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space16
        anchors.rightMargin: Theme.space12
        spacing: Theme.space12
        visible: root.activityState !== "ready" || root.message.length > 0

        FluentIcon {
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            name: root.activityState === "failed" ? "error" : "info"
            iconColor: root.activityState === "failed" ? Theme.danger : Theme.interactive
            iconSize: 15
        }
        Text {
            Layout.fillWidth: true
            text: root.message
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
        PreviewProgress {
            visible: root.progress >= 0
            Layout.preferredWidth: 140
            value: root.progress
        }
        AppButton {
            visible: root.showDetails && root.message.length > 0
            compact: true
            tone: "ghost"
            text: qsTr("Chi tiết")
            onClicked: root.detailsRequested()
        }
    }
}
