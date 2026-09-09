import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestReviewTranslation()
    signal requestUrlImport()
    signal requestDownloadProjectImport()

    readonly property bool editingBatchVideo: AppController.isSelectedBatchVideo
    readonly property bool wideLayout: width >= 980
    property bool activityExpanded: false

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
        anchors.margins: Theme.space12
        spacing: Theme.space12

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: qsTr("Xử lý video")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.section
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            ProjectHeaderActions {
                projectFolderEnabled: AppController.hasOpenProject
                showInputVideo: AppController.hasSelectedVideo
                inputVideoEnabled: AppController.hasSelectedVideo
                showOutputFolder: AppController.hasSelectedVideo
                outputFolderEnabled: AppController.hasSelectedVideo
                deleteEnabled: AppController.hasOpenProject
                deleteText: root.editingBatchVideo ? qsTr("Xóa video") : qsTr("Xóa dự án")
                onProjectFolderRequested: AppController.openProjectFolder()
                onInputVideoRequested: AppController.openInputFile()
                onOutputFolderRequested: AppController.openOutputFolder()
                onDeleteRequested: {
                    if (root.editingBatchVideo)
                        AppController.deleteSelectedVideo()
                    else
                        AppController.deleteCurrentProject()
                }
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
            flickableDirection: Flickable.VerticalFlick
            interactive: !root.wideLayout

            GridLayout {
                id: workspaceGrid

                width: workspaceScroll.width
                height: root.wideLayout ? workspaceScroll.height : implicitHeight
                columns: 2
                columnSpacing: Theme.space12
                rowSpacing: Theme.space12

                SourceMediaPanel {
                    Layout.row: root.wideLayout ? 0 : 1
                    Layout.column: 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.minimumWidth: root.wideLayout ? 270 : 0
                    Layout.preferredWidth: root.wideLayout ? 286 : 600
                    Layout.maximumWidth: root.wideLayout ? 320 : 16777215
                    Layout.minimumHeight: implicitHeight
                    Layout.preferredHeight: implicitHeight
                    compact: true
                    onRequestUrlImport: root.requestUrlImport()
                    onRequestDownloadProjectImport: root.requestDownloadProjectImport()
                }

                DubbingSetupPanel {
                    Layout.row: 0
                    Layout.column: root.wideLayout ? 1 : 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.rowSpan: root.wideLayout ? 2 : 1
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: root.wideLayout ? 650 : 0
                    Layout.preferredWidth: root.wideLayout ? 1040 : 600
                    Layout.minimumHeight: 440
                    Layout.preferredHeight: root.wideLayout ? 650 : 620
                }

                ActivityFeed {
                    Layout.row: root.wideLayout ? 1 : 2
                    Layout.column: 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    visible: root.activityExpanded
                    Layout.fillHeight: root.wideLayout && visible
                    Layout.minimumWidth: root.wideLayout ? 270 : 0
                    Layout.minimumHeight: visible ? (root.wideLayout ? 132 : 180) : 0
                    Layout.preferredWidth: root.wideLayout ? 286 : 600
                    Layout.maximumWidth: root.wideLayout ? 320 : 16777215
                    Layout.preferredHeight: visible ? (root.wideLayout ? 168 : 200) : 0
                    // qmllint disable missing-property
                    model: AppController.activityEventModel
                    // qmllint enable missing-property
                }

                ActivityTray {
                    Layout.row: root.wideLayout ? 2 : 3
                    Layout.column: 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    activityState: AppController.selectedStatus === "failed" ? "failed"
                        : AppController.isProcessing ? "processing" : "ready"
                    message: AppController.selectedStatus === "failed"
                        ? AppController.selectedProgressDetail : I18n.runtimeStatus(AppController.statusMessage)
                    progress: AppController.isProcessing ? AppController.selectedProgress / 100 : -1
                    onDetailsRequested: root.activityExpanded = !root.activityExpanded
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
