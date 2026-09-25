pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Flickable {
    id: root

    property var clipData: ({})
    property var subtitleSegment: ({})
    property bool legacySequence: false
    readonly property string trackId: String(clipData.track_id || "")
    readonly property bool audioClip: ["voice", "source-audio", "music"].indexOf(trackId) >= 0
    readonly property bool watermarkClip: String(clipData.clip_id || "") === "watermark-1"
    signal openImageToolRequested()
    signal settingsCommitted()
    signal watermarkSettingsEdited()

    contentWidth: width
    contentHeight: Math.max(height, content.implicitHeight + Theme.space24)
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    ColumnLayout {
        id: content
        x: Theme.space12
        y: Theme.space12
        width: root.width - Theme.space24
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            visible: !root.trackId
            text: qsTr("Chọn phụ đề hoặc âm thanh trên timeline để chỉnh.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            wrapMode: Text.WordWrap
        }

        AudioClipInspector {
            visible: root.audioClip
            Layout.fillWidth: true
            Layout.preferredHeight: root.audioClip ? Math.max(100, root.height - Theme.space24) : 0
            clipData: root.clipData
        }

        ColumnLayout {
            visible: root.trackId === "source-video"
            Layout.fillWidth: true
            Text {
                text: qsTr("Video nguồn")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.section
            }
            Text {
                Layout.fillWidth: true
                text: root.legacySequence
                    ? qsTr("Không thể cắt video nguồn trong project này.")
                    : qsTr("Kéo hai đầu clip để cắt đầu hoặc cuối video.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                wrapMode: Text.WordWrap
            }
        }

        ColumnLayout {
            visible: root.watermarkClip
            Layout.fillWidth: true
            Text {
                text: qsTr("Watermark")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.section
            }
            Loader {
                id: watermarkStyleLoader
                Layout.fillWidth: true
                active: root.watermarkClip && AppController.watermarkKind === "text"
                sourceComponent: Component {
                    ManualWatermarkStyleControls {
                        width: watermarkStyleLoader.width
                        enabled: AppController.canEditSelectedVideo
                        onWatermarkStyleEdited: root.watermarkSettingsEdited()
                    }
                }
            }
            StudioButton {
                visible: root.watermarkClip
                text: qsTr("Tùy chọn khác")
                variant: "secondary"
                onClicked: root.openImageToolRequested()
            }
        }

    }

    ScrollBar.vertical: ScrollBar {
        policy: root.contentHeight > root.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
    }
}
