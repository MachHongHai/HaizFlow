pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string projectTitle: ""
    property bool hasVideo: false
    property bool hasOutput: false
    property bool hasProject: false
    property bool canUndo: false
    property bool canRedo: false
    property bool hasSelection: false
    property bool sourceSelected: false
    property bool comparing: false

    signal undoRequested()
    signal redoRequested()
    signal compareToggled()
    signal exportRequested()
    signal projectFolderRequested()
    signal inputVideoRequested()
    signal videoFolderRequested()
    signal technicalLogRequested()
    signal projectDeleteRequested()
    signal resetWorkspaceRequested()

    implicitHeight: 42
    color: Theme.surface

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.divider
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: Theme.space16
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, historyGroup.x - Theme.space16 * 2)
        text: root.projectTitle
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        font.weight: Font.DemiBold
        elide: Text.ElideMiddle
        textFormat: Text.PlainText
        Accessible.name: root.projectTitle
    }

    RowLayout {
        id: historyGroup
        objectName: "manualHistoryGroup"
        anchors.centerIn: parent
        spacing: Theme.space8

        StudioIconButton {
            objectName: "manualUndoButton"
            visible: root.hasVideo
            controlSize: 40
            iconName: "undo"
            enabled: root.canUndo
            toolTipText: qsTr("Hoàn tác")
            onClicked: root.undoRequested()
        }
        StudioIconButton {
            objectName: "manualRedoButton"
            visible: root.hasVideo
            controlSize: 40
            iconName: "redo"
            enabled: root.canRedo
            toolTipText: qsTr("Làm lại")
            onClicked: root.redoRequested()
        }

        StudioButton {
            objectName: "manualCompareButton"
            visible: root.hasVideo
            text: qsTr("So sánh")
            iconName: "video"
            variant: root.comparing ? "secondary" : "ghost"
            checked: root.comparing
            checkable: true
            toolTipText: qsTr("Hiện hoặc ẩn video nguồn")
            onClicked: root.compareToggled()
        }
    }

    RowLayout {
        anchors.right: parent.right
        anchors.rightMargin: Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space8

        StudioButton {
            objectName: "manualExportButton"
            visible: root.hasVideo
            text: qsTr("Xuất")
            iconName: "open"
            variant: "primary"
            onClicked: root.exportRequested()
        }

        ProjectHeaderActions {
            projectFolderEnabled: root.hasProject
            showInputVideo: true
            inputVideoEnabled: root.hasVideo
            showVideoFolder: false
            videoFolderEnabled: root.hasVideo
            showTechnicalLog: true
            technicalLogEnabled: root.hasVideo
            deleteEnabled: root.hasProject
            onProjectFolderRequested: root.projectFolderRequested()
            onInputVideoRequested: root.inputVideoRequested()
            onVideoFolderRequested: root.videoFolderRequested()
            onTechnicalLogRequested: root.technicalLogRequested()
            onDeleteRequested: root.projectDeleteRequested()
        }
    }
}
