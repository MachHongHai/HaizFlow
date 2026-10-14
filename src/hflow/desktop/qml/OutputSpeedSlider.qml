pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property real speed: 1.0
    signal edited(real value)
    spacing: Theme.space8

    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: qsTr("Tốc độ video đầu ra")
            color: Theme.text
            font.pixelSize: TypeScale.control
        }
        Text {
            text: speedSlider.value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + "×"
            color: Theme.interactive
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
        }
    }
    AppSlider {
        id: speedSlider
        objectName: "outputSpeedSlider"
        Layout.fillWidth: true
        from: 0.25
        to: 3.0
        stepSize: 0.05
        value: root.speed
        Accessible.name: qsTr("Tốc độ video đầu ra")
        onMoved: {
            if (!pressed)
                root.edited(Math.round(value * 100) / 100)
        }
        onPressedChanged: {
            if (!pressed)
                root.edited(Math.round(value * 100) / 100)
        }
    }
}
