import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Có phiên bản HaizFlow mới")
    subtitle: qsTr("Phiên bản %1").arg(AppController.latestAppVersion)
    preferredWidth: 560
    maximumWidth: 620

    Text {
        Layout.fillWidth: true
        text: AppController.appUpdateReleaseNotes.length > 0
            ? AppController.appUpdateReleaseNotes
            : qsTr("Xem ghi chú phát hành và tải bộ cài từ GitHub.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        maximumLineCount: 10
        elide: Text.ElideRight
    }

    footerActions: [
        StudioButton {
            text: qsTr("Để sau")
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Mở trang tải xuống")
            iconName: "open"
            variant: "primary"
            onClicked: {
                AppController.openAppUpdatePage();
                root.close();
            }
        }
    ]
}
