import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string title: ""
    property string statusText: ""
    property bool canGoBack: true
    signal backRequested()
    signal homeRequested()

    implicitHeight: UiMetrics.toolbarHeight
    color: Theme.topBar

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        spacing: Theme.space8

        IconButton {
            glyph: IconCatalog.glyph("back")
            toolTipText: qsTr("Quay lại")
            enabled: root.canGoBack
            onClicked: root.backRequested()
        }
        IconButton {
            glyph: IconCatalog.glyph("home")
            toolTipText: qsTr("Trang chủ")
            onClicked: root.homeRequested()
        }
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 20
            color: Theme.divider
        }
        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
        }
        StatusBadge {
            visible: root.statusText.length > 0
            label: root.statusText
            status: "ready"
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }
}
