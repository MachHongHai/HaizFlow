pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    objectName: "subtitleCueList"
    property var segments: []
    property int selectedIndex: -1
    property real position: -1
    property bool navigationEnabled: true
    property string searchStatus: ""
    signal segmentSelected(int index)
    signal segmentActivated(int index)
    spacing: Theme.space8

    function formatTime(seconds) {
        const value = Math.max(0, Math.round(Number(seconds || 0) * 1000));
        const hours = Math.floor(value / 3600000);
        return (hours > 0 ? String(hours).padStart(2, "0") + ":" : "")
            + String(Math.floor(value / 60000) % 60).padStart(2, "0") + ":"
            + String(Math.floor(value / 1000) % 60).padStart(2, "0") + "."
            + String(value % 1000).padStart(3, "0");
    }
    function revealSelection() {
        if (selectedIndex >= 0 && selectedIndex < segments.length) {
            cueView.forceLayout();
            cueView.positionViewAtIndex(selectedIndex, ListView.Contain);
        }
    }
    function findNext(direction = 1) {
        const query = searchField.text.trim().toLocaleLowerCase();
        if (!query || !navigationEnabled)
            return;
        const origin = selectedIndex >= 0 ? selectedIndex : direction > 0 ? -1 : 0;
        for (let step = 1; step <= segments.length; ++step) {
            const index = ((origin + step * direction) % segments.length + segments.length) % segments.length;
            if (String(segments[index].text || "").toLocaleLowerCase().includes(query)) {
                searchStatus = "";
                segmentSelected(index);
                return;
            }
        }
        searchStatus = qsTr("Không tìm thấy");
    }
    function focusSearch() { searchField.forceActiveFocus(); }
    onSelectedIndexChanged: Qt.callLater(revealSelection)
    onSegmentsChanged: Qt.callLater(revealSelection)

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space4
        StudioField {
            id: searchField
            objectName: "subtitleCueSearch"
            Layout.fillWidth: true
            placeholderText: qsTr("Tìm phụ đề…")
            accessibleName: qsTr("Tìm trong phụ đề")
            onTextEdited: root.searchStatus = ""
            onAccepted: if (!inputMethodComposing) root.findNext()
        }
        StudioIconButton {
            iconName: "back"
            visible: searchField.text.trim().length > 0
            toolTipText: qsTr("Kết quả trước")
            enabled: root.navigationEnabled && searchField.text.trim().length > 0
            onClicked: root.findNext(-1)
        }
        StudioIconButton {
            iconName: "forward"
            visible: searchField.text.trim().length > 0
            toolTipText: qsTr("Kết quả sau")
            enabled: root.navigationEnabled && searchField.text.trim().length > 0
            onClicked: root.findNext()
        }
    }
    Text {
        Layout.fillWidth: true
        visible: root.searchStatus.length > 0
        text: root.searchStatus
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        textFormat: Text.PlainText
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 100
        color: Theme.input
        radius: Theme.radiusSmall
        border.color: Theme.outline
        ListView {
            id: cueView
            objectName: "subtitleCueView"
            anchors.fill: parent
            anchors.margins: 1
            clip: true
            model: root.segments.length
            onHeightChanged: Qt.callLater(root.revealSelection)
            currentIndex: root.selectedIndex
            reuseItems: true
            cacheBuffer: 140
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: ItemDelegate {
                id: cue
                required property int index
                readonly property var segment: root.segments[index] || ({})
                readonly property bool selected: index === root.selectedIndex
                objectName: "subtitleCue_" + index
                width: cueView.width
                implicitHeight: Math.max(66, contentItem.implicitHeight + 20)
                leftPadding: 12
                rightPadding: 16
                topPadding: 10
                bottomPadding: 10
                enabled: root.navigationEnabled
                focusPolicy: Qt.TabFocus
                Accessible.name: qsTr("Phụ đề %1: %2").arg(index + 1).arg(String(segment.text || ""))
                Accessible.role: Accessible.ListItem
                contentItem: ColumnLayout {
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: String(cue.index + 1).padStart(2, "0")
                            color: cue.selected ? Theme.interactive : Theme.textSubtle
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.metadata
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.formatTime(cue.segment.start) + " — " + root.formatTime(cue.segment.end)
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.metadata
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: String(cue.segment.text || "") || qsTr("Phụ đề trống")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.section
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                }
                background: Rectangle {
                    color: cue.selected ? Theme.interactiveMuted
                        : cue.hovered ? Theme.surfaceMuted : "transparent"
                    border.width: cue.visualFocus ? 1 : 0
                    border.color: Theme.controlFocus
                    Rectangle {
                        width: 3
                        height: parent.height
                        visible: cue.selected
                        color: Theme.interactive
                    }
                }
                onClicked: root.segmentSelected(index)
                onDoubleClicked: root.segmentActivated(index)
                Keys.onReturnPressed: root.segmentActivated(index)
                Keys.onEnterPressed: root.segmentActivated(index)
                Keys.onUpPressed: root.segmentSelected(Math.max(0, root.selectedIndex - 1))
                Keys.onDownPressed: root.segmentSelected(Math.min(root.segments.length - 1, root.selectedIndex + 1))
            }
            Text {
                anchors.centerIn: parent
                width: parent.width - 24
                visible: root.segments.length === 0
                text: qsTr("Chưa có phụ đề")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
        }
    }
}
