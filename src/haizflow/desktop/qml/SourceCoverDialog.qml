pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root
    objectName: "sourceCoverDialog"
    modal: true
    expandedWidth: 1000
    expandedHeight: 740
    toolTitle: qsTr("Chỉnh vùng che")
    property var controller: AppController
    property var media: ({})
    property var draftRegion: ({})
    property bool automatic: true
    property var saveHandler: null
    property bool selectedOwner: true
    property string errorText: ""
    readonly property var visibleRegion: automatic ? (media.detectedRegion || ({})) : draftRegion

    function openForSource(snapshot, region) {
        if (!snapshot || !snapshot.videoSource) return;
        media = snapshot;
        automatic = !region || Object.keys(region).length === 0;
        draftRegion = Object.assign({}, automatic ? (snapshot.detectedRegion || ({})) : region);
        if (!draftRegion.width_percent)
            draftRegion = {x_percent: 10, y_percent: 78, width_percent: 80, height_percent: 10};
        errorText = "";
        open();
    }
    function applyDraft() {
        if (typeof saveHandler === "function" && saveHandler(automatic ? ({}) : draftRegion))
            close();
        else
            errorText = qsTr("Không thể lưu. Video đã thay đổi hoặc đang xử lý.");
    }
    onOpened: Qt.callLater(sourcePlayer.refreshPausedFrame)

    Connections {
        target: root.controller
        function onSelectedVideoChanged() {
            if (root.visible && (root.media.projectKey !== root.controller.projectKey
                    || (root.selectedOwner && root.media.videoId !== root.controller.selectedVideoId)))
                root.close();
        }
        function onSourceReplacementRequested(videoId) {
            if (root.visible && videoId === root.media.videoId) root.close();
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space12
        RowLayout {
            Layout.fillWidth: true
            AppCheckBox {
                objectName: "sourceCoverAutomatic"
                text: qsTr("Tự động nhận diện")
                checked: root.automatic
                onToggled: root.automatic = checked
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: root.automatic && !root.visibleRegion.width_percent
                text: qsTr("Nhận diện khi xử lý")
                color: Theme.textMuted
                font.pixelSize: TypeScale.label
            }
        }
        SourceVideoPlayer {
            id: sourcePlayer
            objectName: "sourceCoverPlayer"
            Layout.fillWidth: true
            Layout.fillHeight: true
            source: root.visible ? root.media.videoSource || "" : ""
            thumbnailSource: root.media.thumbnailSource || ""
            showFullscreen: false
            OcrRegionOverlay {
                id: regionOverlay
                objectName: "sourceCoverRegion"
                z: 2
                anchors.fill: parent
                videoRect: sourcePlayer.videoRect
                region: root.visibleRegion
                interactive: true
                enabled: !root.automatic
                editing: !root.automatic
                showOutline: true
                onRegionEdited: function(region) { root.draftRegion = region; }
            }
        }
        UserErrorNotice {
            Layout.fillWidth: true
            title: qsTr("Chưa lưu được vùng che")
            details: root.errorText
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            StudioButton { text: qsTr("Hủy"); onClicked: root.close() }
            StudioButton {
                objectName: "sourceCoverSave"
                text: qsTr("Lưu")
                variant: "primary"
                onClicked: root.applyDraft()
            }
        }
    }
}
