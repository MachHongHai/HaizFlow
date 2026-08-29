pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var projectModel: null
    signal requestNewProject(string projectType)
    signal openProject(int index, string projectType)

    function resetFilters() {
        searchField.clear()
        typeFilter.currentIndex = 0
        statusFilter.currentIndex = 0
        sortMode.currentIndex = 0
        if (root.projectModel) {
            root.projectModel.query = ""
            root.projectModel.typeFilter = "all"
            root.projectModel.statusFilter = "all"
            root.projectModel.sortMode = "activity"
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space12

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: qsTr("Dự án")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.pageTitle
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            StudioButton {
                id: newProjectButton
                variant: "primary"
                text: qsTr("Dự án mới")
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
                    AppMenuItem { text: qsTr("Tự động"); onTriggered: root.requestNewProject("single") }
                    AppMenuItem { text: qsTr("Thủ công"); onTriggered: root.requestNewProject("manual") }
                    AppMenuItem { text: qsTr("Hàng loạt"); onTriggered: root.requestNewProject("batch") }
                    MenuSeparator {}
                    AppMenuItem { text: qsTr("Tải xuống"); onTriggered: root.requestNewProject("download") }
                    AppMenuItem { text: qsTr("Đăng mạng xã hội"); onTriggered: root.requestNewProject("publish") }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            SearchField {
                id: searchField
                Layout.fillWidth: true
                Layout.maximumWidth: 440
                placeholderText: qsTr("Tìm dự án")
                Accessible.name: qsTr("Tìm dự án")
                onTextEdited: if (root.projectModel) root.projectModel.query = text
            }

            AppComboBox {
                id: typeFilter
                Layout.preferredWidth: 190
                model: [qsTr("Mọi loại"), qsTr("Tự động"), qsTr("Thủ công"), qsTr("Hàng loạt"), qsTr("Tải xuống"), qsTr("Đăng mạng xã hội")]
                onActivated: if (root.projectModel)
                    root.projectModel.typeFilter = ["all", "single", "manual", "batch", "download", "publish"][currentIndex]
                Accessible.name: qsTr("Loại dự án")
            }

            AppComboBox {
                id: statusFilter
                Layout.preferredWidth: 154
                model: [qsTr("Mọi trạng thái"), qsTr("Đang xử lý"), qsTr("Tạm dừng"), qsTr("Hoàn tất"), qsTr("Lỗi")]
                onActivated: if (root.projectModel)
                    root.projectModel.statusFilter = ["all", "processing", "paused", "done", "failed"][currentIndex]
                Accessible.name: qsTr("Trạng thái dự án")
            }

            AppComboBox {
                id: sortMode
                Layout.preferredWidth: 166
                model: [qsTr("Hoạt động gần đây"), qsTr("Tên")]
                onActivated: if (root.projectModel)
                    root.projectModel.sortMode = currentIndex === 0 ? "activity" : "name"
                Accessible.name: qsTr("Sắp xếp dự án")
            }
        }

        GridView {
            id: projectGrid
            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space16) / (236 + Theme.space16)))
            readonly property real cellContentWidth: Math.floor(width / columnCount)
            readonly property real cardWidth: Math.min(260, Math.max(190, cellContentWidth - Theme.space16))
            readonly property real cardHeight: Math.round(cardWidth * 0.56 + 64)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.projectModel
            cellWidth: cellContentWidth
            cellHeight: cardHeight + Theme.space16
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true
            keyNavigationEnabled: true

            delegate: ProjectCard {
                width: projectGrid.cardWidth
                height: projectGrid.cardHeight
                onActivated: root.openProject(index, projectType)
                onOpenRequested: root.openProject(index, projectType)
                onProjectFolderRequested: {
                    if (AppController.selectProjectFromBrowser(index))
                        AppController.openProjectFolder()
                }
                onDeleteRequested: AppController.deleteProjectFromBrowser(index)
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            EmptyState {
                anchors.centerIn: parent
                visible: projectGrid.count === 0
                title: searchField.text.length > 0 ? qsTr("Không tìm thấy dự án") : qsTr("Chưa có dự án")
                message: searchField.text.length > 0
                    ? qsTr("Thử từ khóa hoặc bộ lọc khác.")
                    : qsTr("Tạo dự án để bắt đầu.")
                StudioButton {
                    variant: "primary"
                    text: searchField.text.length > 0 ? qsTr("Xóa bộ lọc") : qsTr("Dự án mới")
                    onClicked: searchField.text.length > 0 ? root.resetFilters() : root.requestNewProject("single")
                }
            }
        }
    }
}
