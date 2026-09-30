pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var projectModel: null

    signal newProjectRequested(string projectType)
    signal recentProjectRequested(int index, string projectType)
    signal projectsRequested()
    signal downloadsRequested()
    signal publishingRequested()

    function typeLabel(type) {
        if (type === "manual") return qsTr("Thủ công")
        if (type === "batch") return qsTr("Hàng loạt")
        if (type === "download") return qsTr("Tải xuống")
        if (type === "publish") return qsTr("Đăng mạng xã hội")
        return qsTr("Tự động")
    }

    function statusLabel(status) {
        if (status === "done") return qsTr("Hoàn tất")
        if (status === "processing") return qsTr("Đang xử lý")
        if (status === "failed") return qsTr("Lỗi")
        if (status === "paused") return qsTr("Tạm dừng")
        if (status === "awaiting_review") return qsTr("Cần duyệt")
        return qsTr("Sẵn sàng")
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: qsTr("Trang chủ")

            StudioButton {
                id: newProjectButton
                text: qsTr("Dự án mới")
                variant: "primary"
                iconName: "add"
                onClicked: newProjectMenu.open()
                Menu {
                    id: newProjectMenu
                    y: newProjectButton.height + Theme.space4
                    width: 220
                    padding: Theme.space4
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.surfaceElevated
                        border.width: 1
                        border.color: Theme.outlineStrong
                    }
                    AppMenuItem { text: qsTr("Tự động"); onTriggered: root.newProjectRequested("single") }
                    AppMenuItem { text: qsTr("Thủ công"); onTriggered: root.newProjectRequested("manual") }
                    AppMenuItem { text: qsTr("Hàng loạt"); onTriggered: root.newProjectRequested("batch") }
                    MenuSeparator {}
                    AppMenuItem { text: qsTr("Tải xuống"); onTriggered: root.newProjectRequested("download") }
                    AppMenuItem { text: qsTr("Đăng mạng xã hội"); onTriggered: root.newProjectRequested("publish") }
                }
            }
        }

        AppSurface {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: 0
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    Layout.leftMargin: Theme.space12
                    Layout.rightMargin: Theme.space8
                    spacing: Theme.space8

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Dự án gần đây")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.section
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    StudioButton {
                        text: qsTr("Xem tất cả")
                        variant: "secondary"
                        onClicked: root.projectsRequested()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    Layout.leftMargin: Theme.space12
                    Layout.rightMargin: Theme.space12
                    spacing: Theme.space12

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Dự án")
                        color: Theme.textSubtle
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.preferredWidth: 112
                        text: qsTr("Trạng thái")
                        color: Theme.textSubtle
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.preferredWidth: 108
                        visible: recentList.width >= 690
                        text: qsTr("Cập nhật")
                        color: Theme.textSubtle
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }

                ListView {
                    id: recentList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: root.projectModel
                    clip: true
                    reuseItems: true
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: RecentProjectRow {
                        required property int index

                        width: recentList.width
                        modelIndex: index
                        typeLabel: root.typeLabel(projectType)
                        statusLabel: root.statusLabel(status)
                        onActivated: function(index, projectType) {
                            root.recentProjectRequested(index, projectType)
                        }
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: recentList.contentHeight > recentList.height
                            ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    }
                }

                EmptyState {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: recentList.count === 0
                    iconName: "projects"
                    title: qsTr("Chưa có dự án")
                    message: qsTr("Tạo dự án để bắt đầu.")

                    StudioButton {
                        text: qsTr("Dự án mới")
                        variant: "primary"
                        onClicked: newProjectMenu.popup(this, 0, height + Theme.space4)
                    }
                }
        }
    }
}
