pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Popup {
    id: root

    property string currentColor: "#FFFFFF"
    property int red: 255
    property int green: 255
    property int blue: 255
    property real hue: 0
    property real saturation: 0
    property real brightness: 1
    property bool invalidHex: false
    readonly property string draftColor: "#" + channelHex(red)
        + channelHex(green) + channelHex(blue)
    readonly property color hueColor: Qt.hsva(hue, 1, 1, 1)

    signal colorApplied(string value)

    width: 466
    height: 328
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - height) / 2) : 0
    padding: Theme.space16
    focus: true
    modal: true
    closePolicy: Popup.CloseOnEscape

    function channelHex(value) {
        return Math.max(0, Math.min(255, Math.round(value)))
            .toString(16).padStart(2, "0").toUpperCase();
    }

    function setRgb(nextRed, nextGreen, nextBlue) {
        red = Math.max(0, Math.min(255, Math.round(nextRed)));
        green = Math.max(0, Math.min(255, Math.round(nextGreen)));
        blue = Math.max(0, Math.min(255, Math.round(nextBlue)));
        const r = red / 255;
        const g = green / 255;
        const b = blue / 255;
        const high = Math.max(r, g, b);
        const low = Math.min(r, g, b);
        const delta = high - low;
        brightness = high;
        saturation = high === 0 ? 0 : delta / high;
        if (delta === 0) hue = 0;
        else if (high === r) hue = (((g - b) / delta) % 6 + 6) % 6 / 6;
        else if (high === g) hue = ((b - r) / delta + 2) / 6;
        else hue = ((r - g) / delta + 4) / 6;
        invalidHex = false;
    }

    function setHsv(nextHue, nextSaturation, nextBrightness) {
        hue = Math.max(0, Math.min(1, nextHue));
        saturation = Math.max(0, Math.min(1, nextSaturation));
        brightness = Math.max(0, Math.min(1, nextBrightness));
        const next = Qt.hsva(hue, saturation, brightness, 1);
        red = Math.round(next.r * 255);
        green = Math.round(next.g * 255);
        blue = Math.round(next.b * 255);
        invalidHex = false;
    }

    function setHex(value) {
        const candidate = String(value || "").trim();
        const hex = candidate.startsWith("#") ? candidate : "#" + candidate;
        if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) {
            invalidHex = true;
            return false;
        }
        setRgb(parseInt(hex.slice(1, 3), 16),
            parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16));
        return true;
    }

    onOpened: {
        setHex(currentColor);
        if (invalidHex) setRgb(255, 255, 255);
        hexField.text = draftColor;
    }

    background: Rectangle {
        color: Theme.surfaceElevated
        radius: Theme.radiusSmall
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: qsTr("Chọn màu")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.section
            font.weight: Font.DemiBold
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space12

            Item {
                id: saturationArea
                objectName: "colorSaturationArea"
                Layout.preferredWidth: 232
                Layout.fillHeight: true
                activeFocusOnTab: true
                Accessible.role: Accessible.Slider
                Accessible.name: qsTr("Độ bão hòa và độ sáng")

                Rectangle {
                    anchors.fill: parent
                    color: root.hueColor
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#FFFFFF" }
                        GradientStop { position: 1; color: "#00FFFFFF" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#00000000" }
                        GradientStop { position: 1; color: "#FF000000" }
                    }
                }
                Rectangle {
                    x: root.saturation * (saturationArea.width - width)
                    y: (1 - root.brightness) * (saturationArea.height - height)
                    width: 12
                    height: 12
                    radius: 6
                    color: "transparent"
                    border.width: 2
                    border.color: "white"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.CrossCursor
                    onPressed: function(mouse) {
                        root.setHsv(root.hue, mouse.x / width, 1 - mouse.y / height);
                        hexField.text = root.draftColor;
                    }
                    onPositionChanged: function(mouse) {
                        if (pressed) {
                            root.setHsv(root.hue, mouse.x / width, 1 - mouse.y / height);
                            hexField.text = root.draftColor;
                        }
                    }
                }
                Keys.onPressed: function(event) {
                    const step = event.modifiers & Qt.ShiftModifier ? 0.05 : 0.01;
                    if (event.key === Qt.Key_Left) root.setHsv(root.hue, root.saturation - step, root.brightness);
                    else if (event.key === Qt.Key_Right) root.setHsv(root.hue, root.saturation + step, root.brightness);
                    else if (event.key === Qt.Key_Up) root.setHsv(root.hue, root.saturation, root.brightness + step);
                    else if (event.key === Qt.Key_Down) root.setHsv(root.hue, root.saturation, root.brightness - step);
                    else return;
                    hexField.text = root.draftColor;
                    event.accepted = true;
                }
            }

            Item {
                id: hueArea
                objectName: "colorHueArea"
                Layout.preferredWidth: 18
                Layout.fillHeight: true
                activeFocusOnTab: true
                Accessible.role: Accessible.Slider
                Accessible.name: qsTr("Sắc độ")

                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#FF0000" }
                        GradientStop { position: 0.167; color: "#FFFF00" }
                        GradientStop { position: 0.333; color: "#00FF00" }
                        GradientStop { position: 0.5; color: "#00FFFF" }
                        GradientStop { position: 0.667; color: "#0000FF" }
                        GradientStop { position: 0.833; color: "#FF00FF" }
                        GradientStop { position: 1; color: "#FF0000" }
                    }
                }
                Rectangle {
                    x: -2
                    y: root.hue * (hueArea.height - height)
                    width: hueArea.width + 4
                    height: 4
                    color: Theme.text
                    border.width: 1
                    border.color: Theme.window
                }
                MouseArea {
                    anchors.fill: parent
                    onPressed: function(mouse) {
                        root.setHsv(mouse.y / height, root.saturation, root.brightness);
                        hexField.text = root.draftColor;
                    }
                    onPositionChanged: function(mouse) {
                        if (pressed) {
                            root.setHsv(mouse.y / height, root.saturation, root.brightness);
                            hexField.text = root.draftColor;
                        }
                    }
                }
                Keys.onPressed: function(event) {
                    if (event.key !== Qt.Key_Up && event.key !== Qt.Key_Down) return;
                    root.setHsv(root.hue + (event.key === Qt.Key_Down ? 0.01 : -0.01),
                        root.saturation, root.brightness);
                    hexField.text = root.draftColor;
                    event.accepted = true;
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.space8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        color: root.currentColor
                        border.width: 1
                        border.color: Theme.outlineStrong
                        Accessible.name: qsTr("Màu hiện tại")
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        color: root.draftColor
                        border.width: 1
                        border.color: Theme.outlineStrong
                        Accessible.name: qsTr("Màu mới")
                    }
                }

                Repeater {
                    model: ["R", "G", "B"]
                    delegate: RowLayout {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true
                        spacing: Theme.space4
                        SettingLabel { text: modelData }
                        NumericField {
                            objectName: "rgbChannel" + index
                            Layout.fillWidth: true
                            from: 0
                            to: 255
                            value: index === 0 ? root.red : index === 1 ? root.green : root.blue
                            onValueModified: {
                                root.setRgb(index === 0 ? value : root.red,
                                    index === 1 ? value : root.green,
                                    index === 2 ? value : root.blue);
                                hexField.text = root.draftColor;
                            }
                        }
                    }
                }

                SettingLabel { text: qsTr("HEX") }
                AppTextField {
                    id: hexField
                    objectName: "colorHexField"
                    Layout.fillWidth: true
                    maximumLength: 7
                    accessibleName: qsTr("Mã màu HEX")
                    onEditingFinished: root.setHex(text)
                }
                Text {
                    visible: root.invalidHex
                    text: qsTr("Nhập 6 ký tự HEX.")
                    color: Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                }
                Item { Layout.fillHeight: true }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            StudioButton {
                text: qsTr("Hủy")
                variant: "secondary"
                onClicked: root.close()
            }
            StudioButton {
                objectName: "applyRgbColor"
                text: qsTr("Áp dụng")
                variant: "primary"
                onClicked: {
                    if (!root.setHex(hexField.text)) return;
                    root.colorApplied(root.draftColor);
                    root.close();
                }
            }
        }
    }
}
