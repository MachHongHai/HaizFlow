pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property var style: ({})
    property bool karaokeEnabled: false
    property string fontLanguage: "vi"
    property int maximumOutline: 20
    signal changeRequested(var patch)

    spacing: Theme.space12

    Loader {
        Layout.fillWidth: true
        active: root.karaokeEnabled
        sourceComponent: Component {
            SubtitleFontPicker {
                family: String(root.style.font_family || "Bangers")
                language: root.fontLanguage
                onFontSelected: function(value) { root.changeRequested({ "font_family": value }) }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        AppCheckBox {
            objectName: "compactBoldToggle"
            text: qsTr("Đậm")
            checked: Number(root.style.font_weight || 400) >= 600
            onToggled: root.changeRequested({ "font_weight": checked ? 700 : 400 })
        }
        AppCheckBox {
            objectName: "compactItalicToggle"
            text: qsTr("Nghiêng")
            checked: Boolean(root.style.italic)
            onToggled: root.changeRequested({ "italic": checked })
        }
    }

    TextColorStrip {
        objectName: "subtitleTextColorStrip"
        Layout.fillWidth: true
        label: qsTr("Màu chữ")
        selectedColor: String(root.style.text_color || "#FFFFFF")
        onColorSelected: function(value) { root.changeRequested({ "text_color": value }) }
    }

    TextColorStrip {
        objectName: "subtitleKaraokeColorStrip"
        Layout.fillWidth: true
        visible: root.karaokeEnabled
        label: qsTr("Màu karaoke")
        selectedColor: String(root.style.karaoke_color || "#FFEF00")
        onColorSelected: function(value) { root.changeRequested({ "karaoke_color": value }) }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        SettingLabel {
            Layout.fillWidth: true
            text: qsTr("Viền")
        }
        NumericField {
            objectName: "compactOutlineWidth"
            from: 0
            to: root.maximumOutline
            value: Math.round(Number(root.style.outline_width || 0))
            suffix: " px"
            onValueModified: root.changeRequested({ "outline_width": value })
        }
    }

    TextColorStrip {
        objectName: "subtitleOutlineColorStrip"
        Layout.fillWidth: true
        visible: root.karaokeEnabled
        label: qsTr("Màu viền")
        colors: ["#000000", "#FFFFFF", "#4A2516"]
        selectedColor: String(root.style.outline_color || "#000000")
        onColorSelected: function(value) { root.changeRequested({ "outline_color": value }) }
    }
}
