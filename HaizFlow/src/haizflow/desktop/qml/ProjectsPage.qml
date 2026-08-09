pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property string projectType: "single"
    property var projectModel: null
    signal requestNewProject()
    signal openProject(string projectType)

    readonly property bool downloadMode: projectType === "download"

    opacity: visible ? 1 : 0
    transform: Translate {
        y: root.visible ? 0 : 8
        Behavior on y {
            NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    Behavior on opacity {
        NumberAnimation { duration: Theme.motionStandard }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

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
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space20
            Layout.topMargin: Theme.space20
            model: root.projectModel
            cellWidth: cellContentWidth
            cellHeight: cardHeight + Theme.space16
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            Component {
                id: newProjectCardDelegate

                Rectangle {
                    id: newProjectCard

                    width: projectGrid.cardWidth
                    height: projectGrid.cardHeight
                    radius: Theme.radius
                    color: newProjectHover.hovered ? Theme.interactiveMuted : Theme.surfaceElevated
                    border.width: activeFocus ? 2 : 1
                    border.color: activeFocus || newProjectHover.hovered ? Theme.focus : Theme.outline
                    focusPolicy: Qt.TabFocus
                    Accessible.role: Accessible.Button
                    Accessible.name: root.projectType === "batch"
                        ? I18n.t("New batch project")
                        : root.downloadMode
                            ? I18n.t("New download project")
                            : I18n.t("New single project")
                    scale: newProjectTap.pressed ? 0.99 : 1

                    Keys.onReturnPressed: root.requestNewProject()
                    Keys.onSpacePressed: root.requestNewProject()

                    HoverHandler {
                        id: newProjectHover
                        cursorShape: Qt.PointingHandCursor
                    }

                    TapHandler {
                        id: newProjectTap
                        onTapped: {
                            root.requestNewProject()
                        }
                    }

                    Column {
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 40, 230)
                        spacing: Theme.space12

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 32
                            height: 32
                            radius: 16
                            color: Theme.interactive

                            AppIcon {
                                anchors.centerIn: parent
                                width: 14
                                height: 14
                                glyph: "\uE710"
                                iconColor: Theme.textOnAccent
                                iconSize: Theme.iconSmall
                            }
                        }

                        Text {
                            width: parent.width
                            text: root.projectType === "batch"
                                ? I18n.t("New batch project")
                                : root.downloadMode
                                    ? I18n.t("New download project")
                                    : I18n.t("New single project")
                            color: Theme.text
                            font.pixelSize: Theme.bodyLarge
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            width: parent.width
                            text: root.projectType === "batch"
                                ? I18n.t("Process videos in batch")
                                : root.downloadMode
                                    ? I18n.t("Channels, videos, and audio")
                                    : I18n.t("Process one video")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            wrapMode: Text.NoWrap
                        }
                    }

                    Behavior on color {
                        ColorAnimation { duration: Theme.motionFast }
                    }
                    Behavior on scale {
                        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
                    }
                }
            }

            delegate: Item {
                id: projectGridDelegate

                required property int index
                required property bool isCreateCard
                required property string projectName
                required property string projectType
                required property int videoCount
                required property string status
                required property int progress
                required property string thumbnailSource
                required property string videoSize

                width: projectGrid.cardWidth
                height: projectGrid.cardHeight

                function resetFocusState() {
                    projectGridDelegate.focus = false
                    projectCard.resetFocusState()
                    if (newProjectCardLoader.item)
                        newProjectCardLoader.item.focus = false
                }

                GridView.onPooled: {
                    visible = false
                    resetFocusState()
                }
                GridView.onReused: {
                    visible = true
                    resetFocusState()
                }

                Loader {
                    id: newProjectCardLoader
                    anchors.fill: parent
                    active: projectGridDelegate.isCreateCard
                    sourceComponent: newProjectCardDelegate
                }

                ProjectCard {
                    id: projectCard
                    visible: !projectGridDelegate.isCreateCard
                    width: parent.width
                    height: parent.height
                    index: projectGridDelegate.index - 1
                    projectName: projectGridDelegate.projectName
                    projectType: projectGridDelegate.projectType
                    videoCount: projectGridDelegate.videoCount
                    status: projectGridDelegate.status
                    progress: projectGridDelegate.progress
                    thumbnailSource: projectGridDelegate.thumbnailSource
                    videoSize: projectGridDelegate.videoSize
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
                        if (AppController.selectProjectInMode(index, root.projectType))
                            AppController.deleteCurrentProject()
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }
}
