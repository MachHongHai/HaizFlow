import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestReviewTranslation()
    signal requestUrlImport()

    readonly property bool wideLayout: width >= 1380

    onWideLayoutChanged: {
        if (wideLayout)
            workspaceScroll.contentY = 0
    }

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
        anchors.margins: Theme.space20
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: AppController.projectName || AppController.selectedFileName || I18n.t("Create a new dub")
            subtitle: AppController.projectDirectory || I18n.t("Turn one source video into a translated, voiced and captioned export.")

            ProjectHeaderActions {
                visible: AppController.hasOpenProject
                projectFolderEnabled: AppController.hasOpenProject
                showInputVideo: AppController.hasSelectedVideo
                inputVideoEnabled: AppController.hasSelectedVideo
                showOutputFolder: AppController.hasSelectedVideo
                outputFolderEnabled: AppController.hasSelectedVideo
                deleteEnabled: AppController.hasOpenProject
                onProjectFolderRequested: AppController.openProjectFolder()
                onInputVideoRequested: AppController.openInputFile()
                onOutputFolderRequested: AppController.openOutputFolder()
                onDeleteRequested: AppController.deleteCurrentProject()
            }
        }

        Flickable {
            id: workspaceScroll

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            clip: true
            contentWidth: width
            contentHeight: root.wideLayout ? height : workspaceGrid.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: root.wideLayout ? Flickable.HorizontalFlick : Flickable.VerticalFlick
            interactive: !root.wideLayout

            GridLayout {
                id: workspaceGrid

                width: workspaceScroll.width
                height: root.wideLayout ? workspaceScroll.height : implicitHeight
                columns: root.wideLayout ? 3 : 2
                columnSpacing: Theme.space16
                rowSpacing: Theme.space16

                SourceMediaPanel {
                    Layout.row: 0
                    Layout.column: 0
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: 390
                    Layout.preferredWidth: root.wideLayout ? 440 : 480
                    Layout.minimumHeight: 460
                    Layout.preferredHeight: 660
                    onRequestUrlImport: root.requestUrlImport()
                }

                DubbingSetupPanel {
                    Layout.row: 0
                    Layout.column: 1
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: 330
                    Layout.preferredWidth: root.wideLayout ? 370 : 440
                    Layout.minimumHeight: 460
                    Layout.preferredHeight: 660
                }

                ActivityLogPanel {
                    Layout.row: root.wideLayout ? 0 : 1
                    Layout.column: root.wideLayout ? 2 : 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: root.wideLayout ? 390 : 0
                    Layout.minimumHeight: root.wideLayout ? 460 : 260
                    Layout.preferredWidth: 540
                    Layout.preferredHeight: root.wideLayout ? 660 : 300
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: root.wideLayout ? ScrollBar.AlwaysOff : ScrollBar.AsNeeded
            }
        }

        VideoCommandBar {
            Layout.fillWidth: true
            onRequestReviewTranslation: root.requestReviewTranslation()
        }
    }
}
