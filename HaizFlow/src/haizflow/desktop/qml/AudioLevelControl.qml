import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string label: ""
    property int volume: 100
    property bool adjustable: true
    property string disabledHint: ""
    signal volumeEdited(int volume)

    Layout.fillWidth: true
    spacing: Theme.space4

    RowLayout {
        Layout.fillWidth: true

        Text {
            Layout.fillWidth: true
            text: root.label
            color: root.adjustable ? Theme.textMuted : Theme.textSubtle
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        Text {
            text: qsTr("%1%").arg(root.volume)
            color: root.adjustable ? Theme.text : Theme.textSubtle
            font.pixelSize: Theme.caption
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }

    AppSlider {
        Layout.fillWidth: true
        enabled: root.adjustable
        from: 0
        to: 100
        stepSize: 1
        value: root.volume
        Accessible.name: root.label
        onMoved: root.volumeEdited(Math.round(value))
    }

    Text {
        Layout.fillWidth: true
        visible: !root.adjustable && root.disabledHint.length > 0
        text: root.disabledHint
        color: Theme.textSubtle
        font.pixelSize: Theme.caption
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
}
