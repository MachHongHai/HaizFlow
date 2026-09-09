import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    default property alias toolContent: body.data
    property string toolTitle: ""
    property string toolSubtitle: ""
    property int expandedWidth: 900
    property int expandedHeight: 700
    property bool openMaximized: false
    property bool maximized: false
    property real restoreX: 0
    property real restoreY: 0

    modal: false
    focus: true
    parent: Overlay.overlay
    width: maximized && parent ? Math.max(320, parent.width - 16)
                               : Math.min(expandedWidth, parent ? parent.width - 32 : expandedWidth)
    height: maximized && parent ? Math.max(180, parent.height - 16)
                                : Math.min(expandedHeight, parent ? parent.height - 32 : expandedHeight)
    padding: 0
    closePolicy: Popup.CloseOnEscape
    header: null
    footer: null

    function placeInCenter() {
        if (!parent)
            return
        x = Math.round((parent.width - width) / 2)
        y = Math.round((parent.height - height) / 2)
    }

    function toggleMaximized() {
        if (!parent)
            return
        if (!maximized) {
            restoreX = x
            restoreY = y
            maximized = true
            x = 8
            y = 8
        } else {
            maximized = false
            Qt.callLater(function() {
                root.x = Math.max(0, Math.min(root.parent.width - root.width, root.restoreX))
                root.y = Math.max(0, Math.min(root.parent.height - root.height, root.restoreY))
            })
        }
    }

    function maximize() {
        if (!parent || maximized)
            return
        restoreX = x
        restoreY = y
        maximized = true
        x = 8
        y = 8
    }

    Connections {
        target: root

        function onOpened() {
            if (root.openMaximized)
                Qt.callLater(root.maximize)
            else
                root.placeInCenter()
        }

        function onClosed() {
            root.maximized = false
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.985; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
    }

    background: Rectangle {
        color: Theme.surface
        border.width: 1
        border.color: root.activeFocus ? Theme.focus : Theme.outlineStrong
        radius: Theme.radius
    }

    contentItem: ColumnLayout {
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property real previousX: 0
                property real previousY: 0
                onPressed: function(mouse) {
                    previousX = mouse.x
                    previousY = mouse.y
                }
                onPositionChanged: function(mouse) {
                    if (!pressed || !root.parent || root.maximized)
                        return
                    root.x = Math.max(0, Math.min(root.parent.width - root.width,
                                                  root.x + mouse.x - previousX))
                    root.y = Math.max(0, Math.min(root.parent.height - root.height,
                                                  root.y + mouse.y - previousY))
                }
                onDoubleClicked: root.toggleMaximized()
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space20
                anchors.rightMargin: Theme.space12
                spacing: Theme.space8

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: root.toolTitle
                        color: Theme.text
                        font.pixelSize: Theme.h3
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: root.toolSubtitle.length > 0
                        text: root.toolSubtitle
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                }

                IconButton {
                    glyph: root.maximized ? "\uE923" : "\uE922"
                    toolTipText: root.maximized ? qsTr("Khôi phục") : qsTr("Phóng to")
                    onClicked: root.toggleMaximized()
                }

                IconButton {
                    glyph: "\uE711"
                    toolTipText: qsTr("Đóng")
                    onClicked: root.close()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Item {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
