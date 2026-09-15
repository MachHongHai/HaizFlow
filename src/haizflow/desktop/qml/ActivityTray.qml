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

    function stateLabel(state) {
        if (state === "failed") return qsTr("Có lỗi");
        if (state === "processing") return qsTr("Đang xử lý");
        if (state === "paused") return qsTr("Đã tạm dừng");
        if (state === "queued") return qsTr("Đang chờ");
        return qsTr("Sẵn sàng");
    }

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 2
        color: root.activityState === "failed" ? Theme.danger
            : root.activityState === "processing" ? Theme.interactive
            : root.activityState === "paused" || root.activityState === "queued"
                ? Theme.warning : Theme.success
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space16
        anchors.rightMargin: Theme.space12
        spacing: Theme.space12
        visible: true

        FluentIcon {
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            name: root.activityState === "failed" ? "error" : "info"
            iconColor: root.activityState === "failed" ? Theme.danger
                : root.activityState === "processing" ? Theme.interactive
                : root.activityState === "paused" || root.activityState === "queued"
                    ? Theme.warning : Theme.success
            iconSize: 15
        }
        Text {
            text: root.stateLabel(root.activityState)
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
        Rectangle {
            visible: root.message.length > 0
            Layout.preferredWidth: 1
            Layout.preferredHeight: 14
            color: Theme.divider
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
        Text {
            visible: root.progress >= 0
            Layout.preferredWidth: 38
            text: Math.round(root.progress * 100) + "%"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            horizontalAlignment: Text.AlignRight
            textFormat: Text.PlainText
        }
        StudioButton {
            visible: root.showDetails && root.activityState !== "ready"
            variant: "ghost"
            text: qsTr("Chi tiết")
            onClicked: root.detailsRequested()
        }
    }
}
