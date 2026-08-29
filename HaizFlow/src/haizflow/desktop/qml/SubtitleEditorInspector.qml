pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property var segment: null
    property int selectedIndex: -1
    property int segmentCount: 0
    property alias editorText: subtitleText.text

    signal previousRequested()
    signal nextRequested()
    signal textCommitted(string value)

    function formatTime(secondsValue) {
        const totalMs = Math.max(0, Math.round((Number(secondsValue) || 0) * 1000));
        const minutes = Math.floor(totalMs / 60000);
        const seconds = Math.floor((totalMs % 60000) / 1000);
        const millis = totalMs % 1000;
        return String(minutes).padStart(2, "0") + ":"
            + String(seconds).padStart(2, "0") + "."
            + String(millis).padStart(3, "0");
    }

    function setEditorText(value) {
        commitTimer.stop();
        subtitleText.text = String(value || "");
    }

    function commitPendingText() {
        commitTimer.stop();
        if (root.segment && subtitleText.text !== String(root.segment.text || ""))
            root.textCommitted(subtitleText.text);
    }

    color: Theme.surfaceElevated
    radius: Theme.radiusSmall
    border.width: 1
    border.color: Theme.outline
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: root.segment
                        ? qsTr("Đoạn %1/%2").arg(root.selectedIndex + 1).arg(root.segmentCount)
                        : qsTr("Chưa chọn phụ đề")
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                }

                Text {
                    Layout.fillWidth: true
                    text: root.segment
                        ? root.formatTime(root.segment.start) + "  —  " + root.formatTime(root.segment.end)
                        : ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.family: "Cascadia Mono"
                }
            }

            StudioIconButton {
                iconName: "back"
                toolTipText: qsTr("Phụ đề trước")
                enabled: root.selectedIndex > 0
                onClicked: root.previousRequested()
            }

            StudioIconButton {
                iconName: "forward"
                toolTipText: qsTr("Phụ đề sau")
                enabled: root.selectedIndex >= 0 && root.selectedIndex < root.segmentCount - 1
                onClicked: root.nextRequested()
            }
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("Nội dung phụ đề")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
        }

        AppTextArea {
            id: subtitleText
            Layout.fillWidth: true
            Layout.fillHeight: true
            enabled: root.segment !== null
            placeholderText: qsTr("Nội dung phụ đề")
            accessibleName: qsTr("Nội dung phụ đề")
            selectByMouse: true

            // Editor history is global; child TextArea history must not consume it.
            Keys.priority: Keys.BeforeItem
            Keys.onPressed: function (event) {
                const controlHeld = (event.modifiers & Qt.ControlModifier) !== 0;
                if (controlHeld && (event.key === Qt.Key_Z || event.key === Qt.Key_Y))
                    event.accepted = true;
            }
            onEditingFinished: root.commitPendingText()
            onTextChanged: {
                if (activeFocus && root.segment && text !== String(root.segment.text || ""))
                    commitTimer.restart();
            }
        }
    }

    Timer {
        id: commitTimer
        interval: 300
        repeat: false
        onTriggered: root.commitPendingText()
    }
}
