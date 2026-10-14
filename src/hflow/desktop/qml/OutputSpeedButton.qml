pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import "."

StudioButton {
    id: root
    property real speed: 1.0
    property bool compactLabel: false
    signal edited(real value)
    readonly property string speedLabel: speed.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + "×"
    text: root.compactLabel ? root.speedLabel : qsTr("Tốc độ %1").arg(root.speedLabel)
    toolTipText: qsTr("Tốc độ video khi xuất")
    variant: "ghost"
    implicitWidth: root.compactLabel ? 64 : 124
    onClicked: {
        if (speedPopup.opened) speedPopup.close();
        else speedPopup.open();
    }
    Popup {
        id: speedPopup
        objectName: "outputSpeedPopup"
        enabled: root.enabled
        x: root.width - width
        y: root.height + Theme.space8
        width: 340
        padding: Theme.space16
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        background: Rectangle {
            color: Theme.surface
            radius: Theme.radius
            border.color: Theme.outline
        }
        contentItem: OutputSpeedSlider {
            speed: root.speed
            onEdited: function(value) {
                if (root.enabled)
                    root.edited(value);
            }
        }
    }
}
