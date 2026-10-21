pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property var segment: null
    property var segments: []
    property int selectedIndex: -1
    property real position: -1
    property int segmentCount: 0
    property alias editorText: subtitleText.text
    readonly property bool textEditing: subtitleText.activeFocus || subtitleText.inputMethodComposing

    signal previousRequested()
    signal nextRequested()
    signal textCommitted(string value)
    signal segmentSelected(int index)

    Shortcut {
        sequence: "Ctrl+F"
        enabled: root.visible
        onActivated: cueList.focusSearch()
    }
    Shortcut {
        sequence: "Alt+Up"
        enabled: root.visible && root.selectedIndex > 0
        onActivated: root.previousRequested()
    }
    Shortcut {
        sequence: "Alt+Down"
        enabled: root.visible && root.selectedIndex + 1 < root.segmentCount
        onActivated: root.nextRequested()
    }

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
        const nextText = String(value || "");
        // Model echoes must not reinstall text: doing so resets cursor/undo
        // and may discard a live pre-edit word even when text is unchanged.
        if (subtitleText.text === nextText)
            return;
        if (subtitleText.activeFocus && subtitleText.inputMethodComposing) {
            // qmllint disable missing-property
            Qt.inputMethod.commit();
            // qmllint enable missing-property
        }
        subtitleText.text = nextText;
    }

    function commitPendingText(finishComposition = true) {
        commitTimer.stop();
        if (subtitleText.inputMethodComposing) {
            if (finishComposition && subtitleText.activeFocus) {
                // qmllint disable missing-property
                Qt.inputMethod.commit();
                // qmllint enable missing-property
            }
            if (subtitleText.inputMethodComposing)
                return;
        }
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

        SubtitleCueList {
            id: cueList
            Layout.fillWidth: true
            Layout.fillHeight: true
            segments: root.segments
            selectedIndex: root.selectedIndex
            position: root.position
            onSegmentSelected: index => root.segmentSelected(index)
            onSegmentActivated: index => {
                root.segmentSelected(index);
                Qt.callLater(subtitleText.forceActiveFocus);
            }
        }

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

        AppTextArea {
            id: subtitleText
            objectName: "autoSubtitleTextInput"
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            Layout.minimumHeight: 72
            Layout.maximumHeight: 104
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
                if (activeFocus && !inputMethodComposing && root.segment && text !== String(root.segment.text || ""))
                    commitTimer.restart();
            }
            onInputMethodComposingChanged: {
                if (inputMethodComposing)
                    commitTimer.stop();
                else if (activeFocus && root.segment && text !== String(root.segment.text || ""))
                    commitTimer.restart();
            }
        }
    }

    Timer {
        id: commitTimer
        interval: 300
        repeat: false
        onTriggered: root.commitPendingText(false)
    }
}
