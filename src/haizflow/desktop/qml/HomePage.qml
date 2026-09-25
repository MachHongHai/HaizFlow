pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var projectModel: null
    readonly property int sidePanelWidth: Math.max(286, Math.min(354, width * 0.31))

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

        AppMenuItem { text: qsTr("Tự động"); onTriggered: root.newProjectRequested("single") }
        AppMenuItem { text: qsTr("Thủ công"); onTriggered: root.newProjectRequested("manual") }
        AppMenuItem { text: qsTr("Hàng loạt"); onTriggered: root.newProjectRequested("batch") }
        MenuSeparator {}
        AppMenuItem { text: qsTr("Tải xuống"); onTriggered: root.newProjectRequested("download") }
        AppMenuItem { text: qsTr("Đăng mạng xã hội"); onTriggered: root.newProjectRequested("publish") }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: qsTr("Trang chủ")

            StudioButton {
                text: qsTr("Dự án")
                variant: "ghost"
                iconName: "projects"
                onClicked: root.projectsRequested()
            }

            StudioButton {
                text: qsTr("Dự án mới")
                variant: "primary"
                iconName: "add"
                onClicked: newProjectMenu.popup(this, 0, height + Theme.space4)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 142
            Layout.maximumHeight: 142
            spacing: Theme.space12

            HomeHero {
                Layout.fillWidth: true
                Layout.minimumWidth: 420
                Layout.fillHeight: true
            }

            HomeCreatorPanel {
                Layout.preferredWidth: root.sidePanelWidth
                Layout.fillHeight: true
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            spacing: Theme.space8

            HomeActionButton {
                Layout.fillWidth: true
                text: qsTr("Xử lý tự động")
                iconName: "play"
                onClicked: root.newProjectRequested("single")
            }
            HomeActionButton {
                Layout.fillWidth: true
                text: qsTr("Biên tập thủ công")
                iconName: "edit"
                onClicked: root.newProjectRequested("manual")
            }
            HomeActionButton {
                Layout.fillWidth: true
                text: qsTr("Tải nội dung")
                iconName: "download"
                onClicked: root.downloadsRequested()
            }
            HomeActionButton {
                Layout.fillWidth: true
                text: qsTr("Đăng mạng xã hội")
                iconName: "publish"
                onClicked: root.publishingRequested()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space12

            AppSurface {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 430
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
                        variant: "ghost"
                        iconName: "forward"
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
                        Layout.preferredWidth: 94
                        text: qsTr("Trạng thái")
                        color: Theme.textSubtle
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                    Text {
                        Layout.preferredWidth: 138
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

            TutorialPlaceholder {
                Layout.preferredWidth: root.sidePanelWidth
                Layout.fillHeight: true
            }
        }
    }
}
