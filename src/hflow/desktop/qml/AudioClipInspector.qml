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
        }
    }

    ScrollBar.vertical: ScrollBar {}
}
