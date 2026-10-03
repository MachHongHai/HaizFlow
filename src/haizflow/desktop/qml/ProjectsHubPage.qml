pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var projectModel: null
    property string pageTitle: qsTr("Dự án")
    signal requestNewProject(string projectType)
    signal openProject(int index, string projectType)

    function resetFilters() {
        searchField.clear()
        typeFilter.currentIndex = 0
        sortMode.currentIndex = 0
        if (root.projectModel) {
            root.projectModel.query = ""
            root.projectModel.typeFilter = "all"
            root.projectModel.statusFilter = "all"
            root.projectModel.sortMode = "activity"
        }
    }

    function syncFilters() {
        if (!root.projectModel || !searchField || !typeFilter || !sortMode)
            return;
        searchField.text = root.projectModel.query || "";
        typeFilter.currentIndex = Math.max(0, ["all", "single", "manual", "batch", "download", "publish"].indexOf(root.projectModel.typeFilter));
        sortMode.currentIndex = root.projectModel.sortMode === "name" ? 1 : 0;
        root.projectModel.statusFilter = "all";
    }

    Component.onCompleted: syncFilters()
    onVisibleChanged: {
        if (visible)
            syncFilters();
        else {
            searchField.deselect();
            searchField.focus = false;
        }
    }

    MouseArea {
        anchors.fill: parent
        z: 1
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: function (mouse) {
            const local = searchField.mapFromItem(root, mouse.x, mouse.y);
            if (searchField.activeFocus && !searchField.contains(local)) {
                searchField.deselect();
                searchField.focus = false;
                root.forceActiveFocus(Qt.MouseFocusReason);
            }
            mouse.accepted = false;
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: root.pageTitle

            StudioButton {
                id: newProjectButton
                objectName: "newProjectButton"
                variant: "primary"
                text: qsTr("Dự án mới")
                iconName: "add"
                onClicked: newProjectMenu.open()

                Menu {
                    id: newProjectMenu
                    objectName: "newProjectMenu"
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
                objectName: "projectSearchField"
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
            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space20) / (224 + Theme.space20)))
            readonly property real cellContentWidth: Math.floor(width / columnCount)
            readonly property real cardWidth: Math.max(1, cellContentWidth - Theme.space20)
            readonly property real cardHeight: Math.round(cardWidth * 0.56 + 64)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.projectModel
            cellWidth: cellContentWidth
            cellHeight: cardHeight + Theme.space20
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
                onRenameRequested: key => AppController.requestProjectRename(key)
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
