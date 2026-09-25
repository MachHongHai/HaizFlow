pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string fileName: ""
    property bool hasVideo: false
    property bool hasOutput: false
    property bool hasProject: false
    property bool canUndo: false
    property bool canRedo: false
    property bool hasSelection: false
    property bool sourceSelected: false
    property bool comparing: false
    property real zoomFactor: 1

    signal undoRequested()
    signal redoRequested()
    signal zoomChanged(real value)
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
            text: root.fileName
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.DemiBold
            elide: Text.ElideMiddle
            textFormat: Text.PlainText
            Accessible.name: root.fileName
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 22
            color: Theme.divider
            visible: root.hasVideo
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

        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 22
            color: Theme.divider
            visible: root.hasVideo
        }

        Item { Layout.fillWidth: true }

        StudioIconButton {
            visible: root.hasVideo && root.width >= 1180
            controlSize: 40
            iconName: "zoomOut"
            enabled: root.zoomFactor > 1.001
            toolTipText: qsTr("Thu nhỏ dòng thời gian")
            onClicked: root.zoomChanged(Math.max(1, root.zoomFactor / 1.25))
        }
        Text {
            visible: root.hasVideo && root.width >= 1180
            Layout.preferredWidth: 42
            text: Math.round(root.zoomFactor * 100) + "%"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }
        StudioIconButton {
            visible: root.hasVideo && root.width >= 1180
            controlSize: 40
            iconName: "zoomIn"
            enabled: root.zoomFactor < 23.999
            toolTipText: qsTr("Phóng to dòng thời gian")
            onClicked: root.zoomChanged(Math.min(24, root.zoomFactor * 1.25))
        }

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
        StudioIconButton {
            visible: root.hasVideo
            controlSize: 40
            iconName: "reset"
            toolTipText: qsTr("Đặt lại bố cục editor")
            onClicked: root.resetWorkspaceRequested()
        }
    }
}
