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

    Menu {
        id: newProjectMenu

        AppMenuItem {
            text: qsTr("Tự động")
            onTriggered: root.newProjectRequested("single")
        }
        AppMenuItem {
            text: qsTr("Thủ công")
            onTriggered: root.newProjectRequested("manual")
        }
        AppMenuItem {
            text: qsTr("Hàng loạt")
            onTriggered: root.newProjectRequested("batch")
        }
        MenuSeparator {}
        AppMenuItem {
            text: qsTr("Tải xuống")
            onTriggered: root.newProjectRequested("download")
        }
        AppMenuItem {
            text: qsTr("Đăng mạng xã hội")
            onTriggered: root.newProjectRequested("publish")
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space12

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: qsTr("Dự án gần đây")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.pageTitle
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            StudioButton {
                text: qsTr("Tải xuống")
                variant: "ghost"
                iconName: "download"
                onClicked: root.downloadsRequested()
            }

            StudioButton {
                text: qsTr("Đăng mạng xã hội")
                variant: "ghost"
                iconName: "send"
                onClicked: root.publishingRequested()
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 22
                Layout.leftMargin: Theme.space4
                Layout.rightMargin: Theme.space4
                color: Theme.divider
            }

            StudioButton {
                text: qsTr("Dự án mới")
                variant: "primary"
                iconName: "add"
                onClicked: newProjectMenu.popup(this, 0, height + Theme.space4)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        AppSurface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                Layout.leftMargin: Theme.space12
                Layout.rightMargin: Theme.space12
                spacing: Theme.space12

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Dự án")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.preferredWidth: 116
                    text: qsTr("Trạng thái")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
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
                    onActivated: function (index, projectType) {
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

        StudioButton {
            Layout.alignment: Qt.AlignRight
            text: qsTr("Xem tất cả dự án")
            variant: "ghost"
            iconName: "forward"
            onClicked: root.projectsRequested()
        }
    }
}
