import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string tone: "info"
    property string title: ""
    property string message: ""
    property bool busy: false
    readonly property bool issue: ErrorPresentation.isIssue(tone) || ErrorPresentation.technical(message)
    property bool dismissed: false
    onMessageChanged: dismissed = false
    default property alias actions: actionArea.data
    readonly property color accent: tone === "danger" ? Theme.danger
        : tone === "warning" ? Theme.warning
        : tone === "success" ? Theme.success : Theme.interactive

    implicitHeight: dismissed ? 0 : Math.max(52, bannerContent.implicitHeight + 20)
    visible: !dismissed
    color: tone === "danger" ? Theme.dangerMuted
        : tone === "warning" ? Theme.warningMuted
        : tone === "success" ? Theme.successMuted : Theme.interactiveMuted
    border.width: dismissed ? 0 : 1
    border.color: root.accent
    radius: Theme.radiusSmall

    RowLayout {
        id: bannerContent
        visible: !root.dismissed
        anchors.fill: parent
        anchors.margins: 10
        spacing: Theme.space8

        BusyIndicator {
            visible: root.busy
            running: visible
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                visible: root.title.length > 0
                text: root.title
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: root.issue ? ErrorPresentation.summary(root.message) : root.message
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }

        RowLayout {
            id: actionArea
            spacing: Theme.space8
            StudioButton {
                visible: root.issue
                text: qsTr("Chi tiết")
                onClicked: AppController.showErrorDetails(root.title, root.message)
            }
            StudioButton {
                visible: root.issue
                text: qsTr("Xác nhận")
                onClicked: root.dismissed = true
            }
            StudioIconButton {
                visible: root.issue; iconName: "close"; toolTipText: qsTr("Đóng")
                onClicked: root.dismissed = true
            }
        }
    }
}
