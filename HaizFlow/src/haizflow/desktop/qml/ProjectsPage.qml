pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property string projectType: "single"
    property var projectModel: null
    signal requestNewProject
    signal openProject(string projectType)

    function newProjectLabel() {
        return qsTr("Dự án mới")
    }

    function pageTitle() {
        if (projectType === "batch")
            return qsTr("Hàng loạt")
        if (projectType === "manual")
            return qsTr("Thủ công")
        if (projectType === "download")
            return qsTr("Tải xuống")
        if (projectType === "publish")
            return qsTr("Đăng mạng xã hội")
        return qsTr("Tự động")
    }

    opacity: visible ? 1 : 0
    transform: Translate {
        y: root.visible ? 0 : 8
        Behavior on y {
            NumberAnimation {
                duration: Theme.motionStandard
                easing.type: Easing.OutCubic
            }
        }
    }
    Behavior on opacity {
        NumberAnimation {
            duration: Theme.motionStandard
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            title: root.pageTitle()

            StudioButton {
                objectName: "newProjectButton"
                text: root.newProjectLabel()
                iconName: "add"
                variant: "primary"
                onClicked: root.requestNewProject()
            }
        }

        GridView {
            id: projectGrid

            // GridView advances by cellWidth.  Keeping the gap inside each cell prevents
            // the last card from overflowing and silently losing an otherwise valid column.
            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space16) / (200 + Theme.space16)))
            readonly property real cellContentWidth: Math.floor(width / columnCount)
            readonly property real cardWidth: Math.min(220, Math.max(1, cellContentWidth - Theme.space16))
            readonly property real cardHeight: Math.round(cardWidth * 0.56 + 64)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.projectModel
            cellWidth: cellContentWidth
            cellHeight: cardHeight + Theme.space16
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: ProjectCard {
                id: projectCard
                width: projectGrid.cardWidth
                height: projectGrid.cardHeight
                onActivated: {
                    if (AppController.selectProjectInMode(index, root.projectType))
                        root.openProject(root.projectType)
                }
                onOpenRequested: {
                    if (AppController.selectProjectInMode(index, root.projectType))
                        root.openProject(root.projectType)
                }
                onProjectFolderRequested: {
                    if (AppController.selectProjectInMode(index, root.projectType))
                        AppController.openProjectFolder()
                }
                onDeleteRequested: {
                    // Resolve the persisted project before showing a
                    // confirmation. Opening it first changes activity
                    // order and can make this row point at another card.
                    AppController.deleteProjectInMode(index, root.projectType)
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            EmptyState {
                anchors.centerIn: parent
                visible: projectGrid.count === 0
                title: qsTr("Chưa có dự án")
                message: qsTr("Tạo dự án để bắt đầu.")

                StudioButton {
                    text: root.newProjectLabel()
                    iconName: "add"
                    variant: "primary"
                    onClicked: root.requestNewProject()
                }
            }
        }
    }
}
