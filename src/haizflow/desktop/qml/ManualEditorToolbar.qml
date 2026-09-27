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
    signal outputRequested()
    signal exportRequested()
    signal projectFolderRequested()
    signal inputVideoRequested()
    signal outputFolderRequested()
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

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space16
        anchors.rightMargin: Theme.space12
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 100
            Layout.maximumWidth: Math.max(140, root.width * 0.28)
            text: root.projectTitle
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            elide: Text.ElideMiddle
            textFormat: Text.PlainText
            Accessible.name: root.projectTitle
        }

        StudioIconButton {
            visible: root.hasVideo
            controlSize: 40
            iconName: "undo"
            enabled: root.canUndo
            toolTipText: qsTr("Hoàn tác")
            onClicked: root.undoRequested()
        }
        StudioIconButton {
            visible: root.hasVideo
            controlSize: 40
            iconName: "redo"
            enabled: root.canRedo
            toolTipText: qsTr("Làm lại")
            onClicked: root.redoRequested()
        }

        Item { Layout.fillWidth: true }

        StudioButton {
            visible: root.hasVideo
            text: qsTr("So sánh")
            iconName: "video"
            variant: root.comparing ? "secondary" : "ghost"
            checked: root.comparing
            checkable: true
            toolTipText: qsTr("Hiện hoặc ẩn video nguồn")
            onClicked: root.compareToggled()
        }
        StudioButton {
            visible: root.hasVideo
            text: qsTr("Mở video xuất")
            iconName: "play"
            variant: "ghost"
            enabled: root.hasOutput
            onClicked: root.outputRequested()
        }
        StudioButton {
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
            showOutputFolder: true
            outputFolderEnabled: root.hasVideo
            showVideoFolder: true
            videoFolderEnabled: root.hasVideo
            showTechnicalLog: true
            technicalLogEnabled: root.hasVideo
            deleteEnabled: root.hasProject
            onProjectFolderRequested: root.projectFolderRequested()
            onInputVideoRequested: root.inputVideoRequested()
            onOutputFolderRequested: root.outputFolderRequested()
            onVideoFolderRequested: root.videoFolderRequested()
            onTechnicalLogRequested: root.technicalLogRequested()
            onDeleteRequested: root.projectDeleteRequested()
        }
    }
}
