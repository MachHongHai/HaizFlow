import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property int itemRow: -1
    property bool publishAllItems: false

    title: qsTr("Xác nhận đăng")
    subtitle: publishAllItems ? qsTr("Đăng toàn bộ video đang chờ") : qsTr("Đăng video đã chọn")
    preferredWidth: 440
    maximumWidth: 480

    function openForPublish(row, publishAll) {
        itemRow = row
        publishAllItems = publishAll
        open()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        PlatformLogo {
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            platform: AppController.zernioSelectedPlatform
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                text: AppController.zernioSelectedAccountName
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Video sẽ được gửi qua Zernio tới nền tảng này.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Hủy")
            variant: "secondary"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Đăng")
            variant: "primary"
            onClicked: {
                AppController.setZernioPublishConsent(true)
                if (root.publishAllItems)
                    AppController.publishAllTikTokItems()
                else
                    AppController.publishTikTokItem(root.itemRow)
                root.close()
            }
        }
    ]
}
