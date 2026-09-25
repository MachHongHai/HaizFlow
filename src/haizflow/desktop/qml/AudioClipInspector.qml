pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Flickable {
    id: root

    property var clipData: ({})
    readonly property string clipId: String(clipData.clip_id || "")

    contentWidth: width
    contentHeight: content.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    ColumnLayout {
        id: content
        width: root.width
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: String(root.clipData.name || qsTr("Âm thanh"))
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.section
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }

        InspectorSection {
            title: qsTr("Âm lượng")
            PropertyRow {
                label: qsTr("Gain")
                ValueSlider {
                    Layout.preferredWidth: 200
                    from: 0; to: 200; value: Number(root.clipData.volume_percent || 0); suffix: "%"
                    onCommitted: function(beforeValue, value) {
                        AppController.updateClipProperties(root.clipId, {"volume_percent": Math.round(value)});
                    }
                }
            }
            PropertyRow {
                label: qsTr("Fade in")
                NumericField {
                    from: 0; to: Math.max(0, Number(root.clipData.duration_ms || 0))
                    value: Math.round(Number(root.clipData.fade_in_ms || 0)); suffix: " ms"
                    onValueModified: AppController.updateClipProperties(root.clipId, {"fade_in_ms": value})
                }
            }
            PropertyRow {
                label: qsTr("Fade out")
                NumericField {
                    from: 0; to: Math.max(0, Number(root.clipData.duration_ms || 0))
                    value: Math.round(Number(root.clipData.fade_out_ms || 0)); suffix: " ms"
                    onValueModified: AppController.updateClipProperties(root.clipId, {"fade_out_ms": value})
                }
            }
            PropertyRow {
                label: qsTr("Tắt tiếng")
                AppSwitch {
                    checked: Boolean(root.clipData.muted)
                    onToggled: AppController.updateClipProperties(root.clipId, {"muted": checked})
                }
            }
            PropertyRow {
                visible: String(root.clipData.track_id || "") === "music"
                label: qsTr("Lặp nhạc")
                AppSwitch {
                    checked: Boolean(root.clipData.loop)
                    onToggled: AppController.updateClipProperties(root.clipId, {"loop": checked})
                }
            }
        }

        InspectorSection {
            title: qsTr("Thời gian")
            collapsible: true
            expanded: false
            PropertyRow {
                label: qsTr("Bắt đầu")
                NumericField {
                    from: 0; to: 86400000; value: Math.round(Number(root.clipData.start_ms || 0)); suffix: " ms"
                    onValueModified: AppController.moveClip(root.clipId, value, String(root.clipData.track_id || ""))
                }
            }
            PropertyRow {
                label: qsTr("Thời lượng")
                NumericField {
                    from: 1; to: 86400000; value: Math.round(Number(root.clipData.duration_ms || 1)); suffix: " ms"
                    onValueModified: AppController.updateClipProperties(root.clipId, {"duration_ms": value})
                }
            }
        }
    }

    ScrollBar.vertical: ScrollBar {}
}
