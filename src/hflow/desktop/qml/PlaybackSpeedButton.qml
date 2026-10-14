pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

IconButton {
    id: root
    property real speed: 1.0
    signal edited(real value)
    readonly property string speedLabel: speed.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + "×"
    implicitWidth: 42
    toolTipText: qsTr("Chỉnh tốc độ phát preview")
    Accessible.name: qsTr("Tốc độ phát %1").arg(root.speedLabel)
    onClicked: {
        if (speedPopup.opened) speedPopup.close();
        else speedPopup.open();
    }
    contentItem: Text {
        text: root.speedLabel
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: root.enabled ? Theme.textMuted : Theme.textSubtle
        font.pixelSize: Theme.caption
        font.family: Theme.fontFamily
        font.weight: Font.DemiBold
        Accessible.ignored: true
    }
    Popup {
        id: speedPopup
        objectName: "previewSpeedPopup"
        enabled: root.enabled
        width: 280
        y: -height - Theme.space8
        padding: Theme.space12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        onAboutToShow: {
            const origin = root.mapToItem(Overlay.overlay, 0, 0);
            x = Math.min(0, Overlay.overlay.width - origin.x - width - Theme.space8);
        }
        onOpened: speedSlider.forceActiveFocus(Qt.PopupFocusReason)
        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.color: Theme.outlineStrong
        }
        contentItem: ColumnLayout {
            spacing: Theme.space4
            Text {
                text: qsTr("Tốc độ preview")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12
                AppSlider {
                    id: speedSlider
                    objectName: "previewSpeedSlider"
                    property bool dragging: false
                    Layout.fillWidth: true
                    from: 0.25
                    to: 3.0
                    stepSize: 0.05
                    value: root.speed
                    Accessible.name: qsTr("Tốc độ preview")
                    onMoved: {
                        if (!pressed && root.enabled && speedPopup.opened)
                            root.edited(Math.round(value * 100) / 100);
                    }
                    onPressedChanged: {
                        if (pressed) dragging = true;
                        else if (dragging) {
                            dragging = false;
                            if (root.enabled && speedPopup.opened)
                                root.edited(Math.round(value * 100) / 100);
                        }
                    }
                }
                Text {
                    Layout.preferredWidth: 48
                    text: speedSlider.value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + "×"
                    horizontalAlignment: Text.AlignRight
                    color: Theme.interactive
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
