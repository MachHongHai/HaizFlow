pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestReviewTranslation()
    signal requestUrlImport()
    signal requestDownloadProjectImport()

    readonly property bool editingBatchVideo: AppController.isSelectedBatchVideo
    readonly property bool wideLayout: width >= 980
    readonly property ActivityLogDialog technicalLogDialog: technicalLogLoader.item as ActivityLogDialog

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
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            title: AppController.projectName || qsTr("Xử lý video")

            Text {
                visible: root.editingBatchVideo
                text: qsTr("Chỉnh riêng video này")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            ProjectHeaderActions {
                projectFolderEnabled: AppController.hasOpenProject
                showInputVideo: AppController.hasSelectedVideo
                inputVideoEnabled: AppController.hasSelectedVideo
                showTechnicalLog: true
                technicalLogEnabled: AppController.hasSelectedVideo
                deleteEnabled: AppController.hasOpenProject
                deleteText: root.editingBatchVideo ? qsTr("Xóa video") : qsTr("Xóa dự án")
                onProjectFolderRequested: AppController.openProjectFolder()
                onInputVideoRequested: AppController.openInputFile()
                onTechnicalLogRequested: {
                    if (technicalLogLoader.status === Loader.Ready && root.technicalLogDialog)
                        root.technicalLogDialog.open();
                    else
                        technicalLogLoader.active = true;
                }
                onDeleteRequested: {
                    if (root.editingBatchVideo)
                        AppController.deleteSelectedVideo()
                    else
                        AppController.deleteCurrentProject()
                }
            }
        }

        Item {
            id: workspaceBody

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0

            GridLayout {
                id: workspaceGrid

                anchors.fill: parent
                columns: 2
                columnSpacing: Theme.space12
                rowSpacing: Theme.space12

                SourceMediaPanel {
                    Layout.row: root.wideLayout ? 0 : 1
                    Layout.column: 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.minimumWidth: root.wideLayout ? 280 : 0
                    Layout.preferredWidth: root.wideLayout ? 320 : 600
                    Layout.maximumWidth: root.wideLayout ? 400 : 16777215
                    Layout.minimumHeight: implicitHeight
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignTop
                    compact: true
                    onRequestUrlImport: root.requestUrlImport()
                    onRequestDownloadProjectImport: root.requestDownloadProjectImport()
                }

                DubbingSetupPanel {
                    Layout.row: 0
                    Layout.column: root.wideLayout ? 1 : 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.rowSpan: 1
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: root.wideLayout ? 650 : 0
                    Layout.preferredWidth: root.wideLayout ? 1040 : 600
                    Layout.minimumHeight: implicitHeight
                    Layout.preferredHeight: root.wideLayout ? 650 : 620
                }

            }

        }

        VideoCommandBar {
            Layout.fillWidth: true
            onRequestReviewTranslation: root.requestReviewTranslation()
        }
    }

    Loader {
        id: technicalLogLoader
        active: false
        asynchronous: false
        onLoaded: if (status === Loader.Ready && root.technicalLogDialog) root.technicalLogDialog.open()
        sourceComponent: Component {
            ActivityLogDialog {
                logText: AppController.logs
                detailText: AppController.selectedFileName
                onClosed: technicalLogLoader.active = false
            }
        }
    }
}
