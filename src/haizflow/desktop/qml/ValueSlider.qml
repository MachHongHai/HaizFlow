import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property real from: 0
    property real to: 100
    property real value: 0
    property real stepSize: 1
    property string suffix: ""
    property int decimals: 0
    property real gestureStart: value

    signal previewed(real value)
    signal committed(real beforeValue, real value)

    spacing: Theme.space8

    AppSlider {
        id: slider
        Layout.fillWidth: true
        from: root.from
        to: root.to
        value: root.value
        stepSize: root.stepSize
        onPressedChanged: {
            if (pressed)
                root.gestureStart = root.value;
            else if (Math.abs(root.gestureStart - value) > 0.0001)
                root.committed(root.gestureStart, value);
        }
        onMoved: root.previewed(value)
    }

    Text {
        Layout.preferredWidth: 62
        text: Number(root.value).toFixed(root.decimals) + root.suffix
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
    }
}
