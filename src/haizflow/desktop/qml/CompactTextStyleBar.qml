pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property var style: ({})
    property bool karaokeEnabled: false
    property int maximumOutline: 20
    signal changeRequested(var patch)

    spacing: Theme.space12

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
        Layout.fillWidth: true
        label: qsTr("Màu chữ")
        selectedColor: String(root.style.text_color || "#FFFFFF")
        onColorSelected: function(value) { root.changeRequested({ "text_color": value }) }
    }

    TextColorStrip {
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
        Layout.fillWidth: true
        visible: root.karaokeEnabled
        label: qsTr("Màu viền")
        colors: ["#000000", "#FFFFFF", "#4A2516"]
        selectedColor: String(root.style.outline_color || "#000000")
        onColorSelected: function(value) { root.changeRequested({ "outline_color": value }) }
    }
}
